from dataclasses import dataclass
from typing import Any, Literal, Protocol
from urllib.parse import urlparse
from uuid import uuid4

import httpx

from backend.app.config import Settings, get_settings

ProviderTaskStatus = Literal["pending", "running", "succeeded", "failed"]


@dataclass(frozen=True)
class MediaSubmission:
    external_job_id: str
    provider_name: str


@dataclass(frozen=True)
class MediaPollResult:
    status: ProviderTaskStatus
    progress_percent: int
    result: dict[str, Any] | None = None
    error_code: str | None = None
    error_message: str | None = None
    retryable: bool = False


class MediaAdapterError(Exception):
    def __init__(self, code: str, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


class MediaAdapter(Protocol):
    provider_name: str

    def submit(self, *, kind: str, input_snapshot: dict[str, Any]) -> MediaSubmission: ...

    def poll(
        self,
        *,
        kind: str,
        external_job_id: str,
        input_snapshot: dict[str, Any],
    ) -> MediaPollResult: ...


def _valid_https_url(value: object) -> str:
    if not isinstance(value, str):
        raise MediaAdapterError("MEDIA_RESULT_INVALID", "生成结果缺少有效地址", retryable=False)
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc:
        raise MediaAdapterError(
            "MEDIA_RESULT_INVALID", "生成结果地址不是有效 HTTPS URL", retryable=False
        )
    return value


def _parse_image_size(value: str) -> tuple[int, int]:
    normalized = value.lower().replace("*", "x")
    try:
        width, height = (int(part) for part in normalized.split("x", maxsplit=1))
    except (TypeError, ValueError) as exc:
        raise MediaAdapterError(
            "MEDIA_PARAMETERS_INVALID", "图片尺寸格式不正确", retryable=False
        ) from exc
    if not (512 <= width <= 2048 and 512 <= height <= 2048):
        raise MediaAdapterError(
            "MEDIA_PARAMETERS_INVALID", "图片宽高必须在 512～2048 之间", retryable=False
        )
    return width, height


class MockMediaAdapter:
    provider_name = "mock"

    def submit(self, *, kind: str, input_snapshot: dict[str, Any]) -> MediaSubmission:
        del input_snapshot
        return MediaSubmission(
            external_job_id=f"mock-{kind}-{uuid4()}",
            provider_name=self.provider_name,
        )

    def poll(
        self,
        *,
        kind: str,
        external_job_id: str,
        input_snapshot: dict[str, Any],
    ) -> MediaPollResult:
        parameters = input_snapshot.get("parameters") or {}
        model_name = str(input_snapshot.get("model_name") or "mock-media-v1")
        if kind == "image":
            width, height = _parse_image_size(str(parameters.get("size") or "1024x1024"))
            result = {
                "assets": [
                    {
                        "url": f"https://mock.generated.local/{external_job_id}.png",
                        "media_type": "image/png",
                        "width": width,
                        "height": height,
                    }
                ],
                "model_name": model_name,
            }
        else:
            duration = int(parameters.get("duration_seconds") or 5)
            result = {
                "assets": [
                    {
                        "url": f"https://mock.generated.local/{external_job_id}.mp4",
                        "media_type": "video/mp4",
                        "duration_seconds": duration,
                        "size": str(parameters.get("size") or "1280*720"),
                    }
                ],
                "model_name": model_name,
            }
        return MediaPollResult(status="succeeded", progress_percent=100, result=result)


def _dashscope_root(base_url: str) -> str:
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise MediaAdapterError("MEDIA_NOT_CONFIGURED", "模型服务地址未正确配置", retryable=False)
    return f"{parsed.scheme}://{parsed.netloc}/api/v1"


class DashScopeMediaAdapter:
    provider_name = "dashscope"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.api_root = _dashscope_root(self.settings.llm_base_url)

    @property
    def _headers(self) -> dict[str, str]:
        key = self.settings.llm_api_key.get_secret_value()
        if not key:
            raise MediaAdapterError(
                "MEDIA_NOT_CONFIGURED", "媒体生成 API Key 未配置", retryable=False
            )
        return {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "X-DashScope-Async": "enable",
        }

    def _request(self, method: str, url: str, **kwargs) -> dict[str, Any]:
        try:
            response = httpx.request(
                method,
                url,
                headers=self._headers,
                timeout=self.settings.llm_timeout_seconds,
                **kwargs,
            )
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise MediaAdapterError(
                "MEDIA_NETWORK_ERROR", "媒体模型服务访问超时或网络异常", retryable=True
            ) from exc
        try:
            payload = response.json()
        except ValueError as exc:
            raise MediaAdapterError(
                "MEDIA_RESPONSE_INVALID", "媒体模型服务响应格式异常", retryable=True
            ) from exc
        if response.status_code >= 400:
            code = str(payload.get("code") or f"HTTP_{response.status_code}")
            message = str(payload.get("message") or "媒体模型服务拒绝请求")[:1000]
            raise MediaAdapterError(
                f"MEDIA_UPSTREAM_{code}",
                message,
                retryable=response.status_code == 429 or response.status_code >= 500,
            )
        return payload

    def submit(self, *, kind: str, input_snapshot: dict[str, Any]) -> MediaSubmission:
        plan = input_snapshot.get("plan") or {}
        content = plan.get("content") or {}
        parameters = input_snapshot.get("parameters") or {}
        if kind == "image":
            prompt = str(content.get("generation_prompt") or "").strip()
            if not prompt:
                raise MediaAdapterError(
                    "MEDIA_PROMPT_INVALID", "主图方案缺少生图提示词", retryable=False
                )
            size = str(parameters.get("size") or self.settings.image_size).replace("x", "*")
            _parse_image_size(size)
            url = f"{self.api_root}/services/aigc/image-generation/generation"
            body = {
                "model": self.settings.image_model,
                "input": {"messages": [{"role": "user", "content": [{"text": prompt[:12000]}]}]},
                "parameters": {
                    "size": size,
                    "n": 1,
                    "prompt_extend": True,
                    "watermark": False,
                },
            }
        else:
            scenes = content.get("scenes") or []
            scene_text = "；".join(
                f"分镜{item.get('order')}：{item.get('visual')}；口播：{item.get('voiceover')}"
                for item in scenes
                if isinstance(item, dict)
            )
            prompt = (
                f"标题：{content.get('title')}。开场：{content.get('hook')}。"
                f"{scene_text}。结尾引导：{content.get('call_to_action')}。"
            )[:1500]
            if not scenes:
                raise MediaAdapterError("MEDIA_PROMPT_INVALID", "视频脚本缺少分镜", retryable=False)
            duration = int(
                parameters.get("duration_seconds") or self.settings.video_duration_seconds
            )
            size = str(parameters.get("size") or self.settings.video_size)
            url = f"{self.api_root}/services/aigc/video-generation/video-synthesis"
            body = {
                "model": self.settings.video_model,
                "input": {"prompt": prompt},
                "parameters": {
                    "size": size,
                    "duration": duration,
                    "prompt_extend": True,
                    "watermark": False,
                },
            }
        payload = self._request("POST", url, json=body)
        output = payload.get("output") or {}
        task_id = output.get("task_id")
        if not isinstance(task_id, str) or not task_id:
            raise MediaAdapterError(
                "MEDIA_RESPONSE_INVALID", "媒体模型未返回任务编号", retryable=True
            )
        return MediaSubmission(external_job_id=task_id, provider_name=self.provider_name)

    def poll(
        self,
        *,
        kind: str,
        external_job_id: str,
        input_snapshot: dict[str, Any],
    ) -> MediaPollResult:
        payload = self._request("GET", f"{self.api_root}/tasks/{external_job_id}")
        output = payload.get("output") or {}
        provider_status = str(output.get("task_status") or "UNKNOWN").upper()
        if provider_status == "PENDING":
            return MediaPollResult(status="pending", progress_percent=25)
        if provider_status == "RUNNING":
            return MediaPollResult(status="running", progress_percent=60)
        if provider_status in {"FAILED", "CANCELED", "UNKNOWN"}:
            code = str(output.get("code") or f"MEDIA_{provider_status}")
            return MediaPollResult(
                status="failed",
                progress_percent=0,
                error_code=code,
                error_message=str(output.get("message") or "媒体生成任务失败")[:1000],
                retryable=provider_status in {"FAILED", "UNKNOWN"}
                and code in {"InternalError", "MEDIA_UNKNOWN"},
            )
        if provider_status != "SUCCEEDED":
            raise MediaAdapterError(
                "MEDIA_RESPONSE_INVALID", "媒体任务返回未知状态", retryable=True
            )
        usage = payload.get("usage") or {}
        model_name = str(input_snapshot.get("model_name") or "unknown")
        if kind == "image":
            urls: list[str] = []
            for choice in output.get("choices") or []:
                message = choice.get("message") if isinstance(choice, dict) else None
                for item in (message or {}).get("content") or []:
                    if isinstance(item, dict) and item.get("image"):
                        urls.append(_valid_https_url(item["image"]))
            if not urls:
                raise MediaAdapterError(
                    "MEDIA_RESULT_INVALID", "图片任务成功但没有返回图片", retryable=False
                )
            width = int(usage.get("output_width") or 0)
            height = int(usage.get("output_height") or 0)
            if width <= 0 or height <= 0:
                width, height = _parse_image_size(
                    str((input_snapshot.get("parameters") or {}).get("size") or "1024x1024")
                )
            assets = [
                {
                    "url": url,
                    "media_type": "image/png",
                    "width": width,
                    "height": height,
                }
                for url in urls
            ]
        else:
            video_url = _valid_https_url(output.get("video_url"))
            duration = int(
                usage.get("output_video_duration")
                or usage.get("duration")
                or (input_snapshot.get("parameters") or {}).get("duration_seconds")
                or 0
            )
            if duration <= 0:
                raise MediaAdapterError(
                    "MEDIA_RESULT_INVALID", "视频任务成功但缺少有效时长", retryable=False
                )
            assets = [
                {
                    "url": video_url,
                    "media_type": "video/mp4",
                    "duration_seconds": duration,
                    "size": str(usage.get("size") or ""),
                }
            ]
        return MediaPollResult(
            status="succeeded",
            progress_percent=100,
            result={"assets": assets, "model_name": model_name, "usage": usage},
        )


def get_media_adapter(settings: Settings | None = None) -> MediaAdapter:
    resolved = settings or get_settings()
    if resolved.generation_provider == "mock":
        return MockMediaAdapter()
    return DashScopeMediaAdapter(resolved)
