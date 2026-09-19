import base64
import ipaddress
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.parse import urljoin, urlparse
from uuid import uuid4

import httpx

from backend.app.config import Settings, get_settings

ALLOWED_MEDIA_TYPES = frozenset(
    {"image/png", "image/jpeg", "image/webp", "video/mp4", "video/webm"}
)
REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
MOCK_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M/wHwAF/gL+X1ZQAAAAAElFTkSuQmCC"
)
MOCK_MP4 = (
    b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2\x00\x00\x00\x08free\x00\x00\x00\x08mdat"
)


class StorageError(Exception):
    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


@dataclass(frozen=True)
class DownloadedMedia:
    content: bytes
    mime_type: str
    extension: str


class StorageAdapter(Protocol):
    def put_bytes(self, storage_key: str, content: bytes) -> tuple[Path, bool]: ...

    def resolve_path(self, storage_key: str) -> Path: ...

    def exists(self, storage_key: str) -> bool: ...

    def delete(self, storage_key: str) -> None: ...


def _sniff_media_type(content: bytes) -> tuple[str, str]:
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", "png"
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", "jpg"
    if len(content) >= 12 and content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        return "image/webp", "webp"
    if len(content) >= 12 and content[4:8] == b"ftyp":
        return "video/mp4", "mp4"
    if content.startswith(b"\x1a\x45\xdf\xa3"):
        return "video/webm", "webm"
    raise StorageError("ASSET_FILE_TYPE_INVALID", "生成结果不是受支持的图片或视频文件")


def mock_media_bytes(kind: str) -> DownloadedMedia:
    content = MOCK_PNG if kind == "image" else MOCK_MP4
    mime_type, extension = _sniff_media_type(content)
    return DownloadedMedia(content=content, mime_type=mime_type, extension=extension)


class LocalStorageAdapter:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def resolve_path(self, storage_key: str) -> Path:
        relative = Path(storage_key)
        if relative.is_absolute() or not storage_key or ".." in relative.parts:
            raise StorageError("ASSET_STORAGE_KEY_INVALID", "素材存储 Key 非法")
        resolved = (self.root / relative).resolve()
        if resolved != self.root and self.root not in resolved.parents:
            raise StorageError("ASSET_STORAGE_KEY_INVALID", "素材存储 Key 越界")
        return resolved

    def put_bytes(self, storage_key: str, content: bytes) -> tuple[Path, bool]:
        target = self.resolve_path(storage_key)
        target.parent.mkdir(parents=True, exist_ok=True)
        existed = target.exists()
        temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
        try:
            temporary.write_bytes(content)
            temporary.replace(target)
        except OSError as exc:
            temporary.unlink(missing_ok=True)
            raise StorageError(
                "ASSET_STORAGE_WRITE_FAILED", "素材写入本地存储失败", retryable=True
            ) from exc
        return target, not existed

    def exists(self, storage_key: str) -> bool:
        return self.resolve_path(storage_key).is_file()

    def delete(self, storage_key: str) -> None:
        try:
            self.resolve_path(storage_key).unlink(missing_ok=True)
        except OSError as exc:
            raise StorageError(
                "ASSET_STORAGE_DELETE_FAILED", "素材临时文件清理失败", retryable=True
            ) from exc


def _validate_public_https_url(url: str) -> None:
    parsed = urlparse(url)
    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.port not in {None, 443}
    ):
        raise StorageError("ASSET_SOURCE_URL_INVALID", "素材来源必须是标准 HTTPS 地址")
    hostname = parsed.hostname.rstrip(".").lower()
    try:
        addresses = {ipaddress.ip_address(hostname)}
    except ValueError:
        try:
            addresses = {
                ipaddress.ip_address(item[4][0])
                for item in socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
            }
        except (OSError, ValueError) as exc:
            raise StorageError(
                "ASSET_SOURCE_DNS_FAILED", "素材来源域名解析失败", retryable=True
            ) from exc
    if not addresses or any(not address.is_global for address in addresses):
        raise StorageError("ASSET_SOURCE_ADDRESS_BLOCKED", "素材来源地址不允许访问")


class MediaDownloader:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def download(self, url: str, *, kind: str) -> DownloadedMedia:
        max_bytes = (
            self.settings.storage_max_image_bytes
            if kind == "image"
            else self.settings.storage_max_video_bytes
        )
        current_url = url
        timeout = httpx.Timeout(self.settings.storage_download_timeout_seconds)
        try:
            with httpx.Client(timeout=timeout, follow_redirects=False) as client:
                for redirect_count in range(self.settings.storage_max_redirects + 1):
                    _validate_public_https_url(current_url)
                    with client.stream(
                        "GET",
                        current_url,
                        headers={"Accept": "image/*,video/*;q=0.9"},
                    ) as response:
                        if response.status_code in REDIRECT_STATUSES:
                            location = response.headers.get("location")
                            if (
                                not location
                                or redirect_count >= self.settings.storage_max_redirects
                            ):
                                raise StorageError(
                                    "ASSET_SOURCE_REDIRECT_INVALID", "素材来源重定向无效"
                                )
                            current_url = urljoin(current_url, location)
                            continue
                        if response.status_code == 429 or response.status_code >= 500:
                            raise StorageError(
                                "ASSET_SOURCE_UNAVAILABLE",
                                "素材来源服务暂时不可用",
                                retryable=True,
                            )
                        if response.status_code >= 400:
                            raise StorageError(
                                "ASSET_SOURCE_DOWNLOAD_FAILED",
                                f"素材下载失败（HTTP {response.status_code}）",
                            )
                        try:
                            declared_size = int(response.headers.get("content-length") or 0)
                        except ValueError as exc:
                            raise StorageError(
                                "ASSET_SOURCE_RESPONSE_INVALID",
                                "素材来源返回了无效的文件长度",
                            ) from exc
                        if declared_size > max_bytes:
                            raise StorageError("ASSET_FILE_TOO_LARGE", "生成结果文件超过大小限制")
                        chunks: list[bytes] = []
                        received = 0
                        for chunk in response.iter_bytes():
                            received += len(chunk)
                            if received > max_bytes:
                                raise StorageError(
                                    "ASSET_FILE_TOO_LARGE", "生成结果文件超过大小限制"
                                )
                            chunks.append(chunk)
                        content = b"".join(chunks)
                        if not content:
                            raise StorageError("ASSET_FILE_EMPTY", "生成结果文件为空")
                        mime_type, extension = _sniff_media_type(content)
                        declared_type = response.headers.get("content-type", "").split(";", 1)[0]
                        if declared_type and declared_type not in ALLOWED_MEDIA_TYPES | {
                            "application/octet-stream"
                        }:
                            raise StorageError(
                                "ASSET_CONTENT_TYPE_INVALID", "素材来源返回了不安全的内容类型"
                            )
                        if (kind == "image") != mime_type.startswith("image/"):
                            raise StorageError(
                                "ASSET_MEDIA_KIND_MISMATCH", "生成结果媒体类型与任务类型不一致"
                            )
                        return DownloadedMedia(content, mime_type, extension)
        except StorageError:
            raise
        except (httpx.TimeoutException, httpx.NetworkError, OSError) as exc:
            raise StorageError(
                "ASSET_SOURCE_NETWORK_ERROR", "下载生成结果时网络异常", retryable=True
            ) from exc
        raise StorageError("ASSET_SOURCE_REDIRECT_INVALID", "素材来源重定向次数过多")


def get_storage_adapter(settings: Settings | None = None) -> StorageAdapter:
    selected = settings or get_settings()
    if selected.storage_backend != "local":
        raise StorageError("STORAGE_BACKEND_UNSUPPORTED", "当前仅支持本地素材存储")
    return LocalStorageAdapter(selected.storage_local_path)
