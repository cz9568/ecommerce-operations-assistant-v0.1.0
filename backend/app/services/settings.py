import base64
import inspect
import re
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Literal
from urllib.parse import urlparse

from cryptography.fernet import Fernet, InvalidToken
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.api.schemas.settings import SettingsUpdate
from backend.app.config import Settings, get_settings
from backend.app.errors import AppError
from backend.app.models.entities import SystemSetting, User
from backend.app.services.audit import add_audit_log


@dataclass(frozen=True)
class Definition:
    key: str
    group: Literal["model", "system", "queue"]
    label: str
    description: str
    value_type: Literal["string", "integer", "boolean", "decimal", "json"]
    apply_mode: Literal["immediate", "new_requests", "worker_restart", "service_restart"]
    minimum: int | None = None
    maximum: int | None = None
    choices: tuple[str, ...] = ()
    sensitive: bool = False


DEFINITIONS = (
    Definition(
        "llm_model",
        "model",
        "文本模型",
        "普通文本模型名称；mock 会使用本地确定性输出。",
        "string",
        "new_requests",
    ),
    Definition(
        "llm_structured_model",
        "model",
        "结构化模型",
        "诊断、方案、建议和复盘使用的严格结构化模型。",
        "string",
        "new_requests",
    ),
    Definition(
        "llm_base_url", "model", "模型服务地址", "OpenAI 兼容接口根地址。", "string", "new_requests"
    ),
    Definition(
        "llm_api_key",
        "model",
        "模型 API Key",
        "加密保存；查询接口只返回是否已配置。",
        "string",
        "new_requests",
        sensitive=True,
    ),
    Definition(
        "llm_timeout_seconds",
        "model",
        "文本请求超时",
        "单次文本模型请求超时秒数。",
        "integer",
        "new_requests",
        5,
        300,
    ),
    Definition(
        "llm_max_retries",
        "model",
        "文本重试次数",
        "可重试错误的最大重试次数。",
        "integer",
        "new_requests",
        0,
        5,
    ),
    Definition(
        "llm_requests_per_minute",
        "model",
        "每分钟请求数",
        "单进程文本模型限流值。",
        "integer",
        "new_requests",
        1,
        600,
    ),
    Definition(
        "generation_provider",
        "model",
        "媒体 Provider",
        "图片和视频生成 Provider。",
        "string",
        "worker_restart",
        choices=("mock", "dashscope"),
    ),
    Definition(
        "image_model",
        "model",
        "图片模型",
        "异步图片生成使用的模型名称。",
        "string",
        "worker_restart",
    ),
    Definition(
        "image_size",
        "model",
        "默认图片尺寸",
        "格式为宽x高，范围 512～2048。",
        "string",
        "immediate",
    ),
    Definition(
        "video_model",
        "model",
        "视频模型",
        "异步视频生成使用的模型名称。",
        "string",
        "worker_restart",
    ),
    Definition(
        "video_size", "model", "默认视频尺寸", "支持横竖屏 720p/1080p。", "string", "immediate"
    ),
    Definition(
        "video_duration_seconds",
        "model",
        "默认视频时长",
        "支持 5 或 10 秒。",
        "integer",
        "immediate",
        choices=("5", "10"),
    ),
    Definition(
        "competitor_parse_timeout_seconds",
        "system",
        "竞品解析超时",
        "公开页面解析请求超时秒数。",
        "integer",
        "new_requests",
        1,
        60,
    ),
    Definition(
        "competitor_parse_max_bytes",
        "system",
        "竞品响应上限",
        "公开页面最大响应字节数。",
        "integer",
        "new_requests",
        100_000,
        10_000_000,
    ),
    Definition(
        "competitor_parse_max_redirects",
        "system",
        "竞品重定向上限",
        "公开页面最大重定向次数。",
        "integer",
        "new_requests",
        0,
        10,
    ),
    Definition(
        "storage_download_timeout_seconds",
        "system",
        "素材下载超时",
        "供应商素材转存超时秒数。",
        "integer",
        "worker_restart",
        5,
        300,
    ),
    Definition(
        "storage_max_image_bytes",
        "system",
        "图片大小上限",
        "单张图片最大字节数。",
        "integer",
        "worker_restart",
        1_000_000,
        100_000_000,
    ),
    Definition(
        "storage_max_video_bytes",
        "system",
        "视频大小上限",
        "单个视频最大字节数。",
        "integer",
        "worker_restart",
        1_000_000,
        2_000_000_000,
    ),
    Definition(
        "job_max_attempts",
        "queue",
        "任务最大尝试次数",
        "新建生成任务的最大自动尝试次数。",
        "integer",
        "immediate",
        1,
        10,
    ),
    Definition(
        "job_timeout_seconds",
        "queue",
        "任务超时",
        "Worker 判定运行超时的秒数。",
        "integer",
        "worker_restart",
        30,
        7200,
    ),
    Definition(
        "job_poll_interval_seconds",
        "queue",
        "轮询间隔",
        "Worker 外部任务轮询间隔秒数。",
        "integer",
        "worker_restart",
        1,
        60,
    ),
    Definition(
        "job_lock_timeout_seconds",
        "queue",
        "领取锁超时",
        "Worker 锁恢复阈值秒数。",
        "integer",
        "worker_restart",
        10,
        900,
    ),
    Definition(
        "job_worker_concurrency",
        "queue",
        "Worker 并发数",
        "下次启动 Worker 时使用的默认并发数。",
        "integer",
        "worker_restart",
        1,
        16,
    ),
)
BY_KEY = {item.key: item for item in DEFINITIONS}


def _fernet() -> Fernet:
    secret = get_settings().jwt_secret.get_secret_value().encode("utf-8")
    return Fernet(base64.urlsafe_b64encode(sha256(secret).digest()))


def _encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def _decrypt(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError) as exc:
        raise AppError(500, "SETTING_SECRET_INVALID", "敏感配置无法解密，请重新保存") from exc


def _convert(definition: Definition, value: Any) -> Any:
    if definition.sensitive:
        if value is None or value == "":
            return None
        if not isinstance(value, str) or len(value.strip()) < 8:
            raise AppError(422, "SETTING_VALUE_INVALID", f"{definition.label}格式无效")
        return value.strip()
    if definition.value_type == "integer":
        if isinstance(value, bool):
            raise AppError(422, "SETTING_VALUE_INVALID", f"{definition.label}必须是整数")
        try:
            converted = int(value)
        except (TypeError, ValueError) as exc:
            raise AppError(422, "SETTING_VALUE_INVALID", f"{definition.label}必须是整数") from exc
        if definition.minimum is not None and converted < definition.minimum:
            raise AppError(
                422, "SETTING_VALUE_INVALID", f"{definition.label}不能小于 {definition.minimum}"
            )
        if definition.maximum is not None and converted > definition.maximum:
            raise AppError(
                422, "SETTING_VALUE_INVALID", f"{definition.label}不能大于 {definition.maximum}"
            )
        if definition.choices and str(converted) not in definition.choices:
            raise AppError(422, "SETTING_VALUE_INVALID", f"{definition.label}不在允许范围内")
        return converted
    if not isinstance(value, str) or not value.strip() or "\n" in value or "\r" in value:
        raise AppError(422, "SETTING_VALUE_INVALID", f"{definition.label}格式无效")
    converted = value.strip()
    if definition.choices and converted not in definition.choices:
        raise AppError(422, "SETTING_VALUE_INVALID", f"{definition.label}不在允许范围内")
    if definition.key == "llm_base_url" and converted:
        parsed = urlparse(converted)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise AppError(422, "SETTING_VALUE_INVALID", "模型服务地址必须是 HTTP(S) URL")
    if definition.key == "image_size":
        match = re.fullmatch(r"(\d{3,4})[x*](\d{3,4})", converted)
        if not match or any(not 512 <= int(item) <= 2048 for item in match.groups()):
            raise AppError(422, "SETTING_VALUE_INVALID", "图片尺寸必须在 512～2048 之间")
        converted = converted.replace("*", "x")
    if definition.key == "video_size" and converted.replace("x", "*") not in {
        "1280*720",
        "720*1280",
        "1920*1080",
        "1080*1920",
    }:
        raise AppError(422, "SETTING_VALUE_INVALID", "视频尺寸不在允许范围内")
    return converted


def _rows(session: Session) -> dict[str, SystemSetting]:
    return {
        row.setting_key: row
        for row in session.scalars(
            select(SystemSetting).where(SystemSetting.setting_key.in_(BY_KEY))
        ).all()
    }


def resolve_runtime_settings(session: Session) -> Settings:
    base = get_settings()
    updates: dict[str, Any] = {}
    for key, row in _rows(session).items():
        definition = BY_KEY[key]
        value = row.value_json
        if definition.sensitive:
            ciphertext = value.get("ciphertext") if isinstance(value, dict) else None
            if ciphertext:
                updates[key] = SecretStr(_decrypt(str(ciphertext)))
        else:
            updates[key] = value
    return base.model_copy(update=updates)


def configured_text_provider(factory: Any, session: Session) -> Any:
    """Call the normal provider factory while keeping zero-argument test doubles compatible."""
    if not inspect.signature(factory).parameters:
        return factory()
    return factory(resolve_runtime_settings(session))


def settings_response(session: Session) -> dict[str, Any]:
    base = get_settings()
    rows = _rows(session)
    groups: dict[str, list[dict[str, Any]]] = {"model": [], "system": [], "queue": []}
    for definition in DEFINITIONS:
        row = rows.get(definition.key)
        environment_value = getattr(base, definition.key)
        if isinstance(environment_value, SecretStr):
            environment_value = environment_value.get_secret_value()
        configured = bool(row or environment_value)
        groups[definition.group].append(
            {
                "key": definition.key,
                "group": definition.group,
                "label": definition.label,
                "description": definition.description,
                "value_type": definition.value_type,
                "value": None
                if definition.sensitive
                else (row.value_json if row else environment_value),
                "sensitive": definition.sensitive,
                "configured": configured,
                "source": "database" if row else "environment",
                "apply_mode": definition.apply_mode,
                "updated_at": row.updated_at if row else None,
            }
        )
    return {"groups": groups}


def update_settings(
    session: Session,
    *,
    group: str,
    payload: SettingsUpdate,
    actor: User,
    request_id: str | None,
) -> dict[str, Any]:
    if group not in {"model", "system", "queue"}:
        raise AppError(404, "SETTING_GROUP_NOT_FOUND", "配置分组不存在")
    converted: dict[str, Any] = {}
    for key, value in payload.values.items():
        definition = BY_KEY.get(key)
        if definition is None or definition.group != group:
            raise AppError(422, "SETTING_KEY_INVALID", f"配置项 {key} 不属于当前分组")
        normalized = _convert(definition, value)
        if normalized is not None:
            converted[key] = normalized
    if not converted:
        raise AppError(422, "SETTING_NO_CHANGE", "没有可保存的配置变更")
    candidate = resolve_runtime_settings(session).model_copy(
        update={
            key: SecretStr(value) if BY_KEY[key].sensitive else value
            for key, value in converted.items()
        }
    )
    candidate.validate_runtime()
    rows = _rows(session)
    for key, value in converted.items():
        definition = BY_KEY[key]
        stored_value: Any = {"ciphertext": _encrypt(value)} if definition.sensitive else value
        row = rows.get(key)
        if row is None:
            row = SystemSetting(
                setting_key=key,
                value_json=stored_value,
                value_type=definition.value_type,
                description=definition.description,
                is_sensitive=int(definition.sensitive),
                updated_by=actor.id,
            )
            session.add(row)
        else:
            row.value_json = stored_value
            row.value_type = definition.value_type
            row.description = definition.description
            row.is_sensitive = int(definition.sensitive)
            row.updated_by = actor.id
    add_audit_log(
        session,
        actor_user_id=actor.id,
        action="settings.update",
        target_type="system_setting_group",
        target_id=group,
        request_id=request_id,
        detail={
            "changed_keys": sorted(converted),
            "contains_sensitive": any(BY_KEY[key].sensitive for key in converted),
        },
    )
    session.commit()
    return settings_response(session)
