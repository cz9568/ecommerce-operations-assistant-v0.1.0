import json
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
from pydantic import ValidationError

from backend.app.config import Settings, get_settings
from backend.app.integrations.ai.prompts import PromptBundle, _sample


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


@dataclass(frozen=True)
class TextGenerationResult:
    data: dict[str, Any]
    raw_text: str
    provider_name: str
    model_name: str
    usage: TokenUsage
    attempts: int
    latency_ms: int


class AiGenerationError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        attempts: int = 1,
        latency_ms: int = 0,
        usage: TokenUsage | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.attempts = attempts
        self.latency_ms = latency_ms
        self.usage = usage or TokenUsage()


class TextProvider(Protocol):
    provider_name: str
    model_name: str

    def generate_structured(self, prompt: PromptBundle) -> TextGenerationResult: ...


class MockTextProvider:
    provider_name = "mock"
    model_name = "mock-deterministic-v1"

    def generate_structured(self, prompt: PromptBundle) -> TextGenerationResult:
        started = time.monotonic()
        data = _sample(prompt.kind)
        validated = prompt.response_model.model_validate(data).model_dump(mode="json")
        raw = json.dumps(validated, ensure_ascii=False)
        return TextGenerationResult(
            data=validated,
            raw_text=raw,
            provider_name=self.provider_name,
            model_name=self.model_name,
            usage=TokenUsage(),
            attempts=1,
            latency_ms=max(0, int((time.monotonic() - started) * 1000)),
        )


class _RateLimiter:
    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.timestamps: deque[float] = deque()
        self.lock = threading.Lock()

    def acquire(self) -> bool:
        now = time.monotonic()
        with self.lock:
            while self.timestamps and now - self.timestamps[0] >= 60:
                self.timestamps.popleft()
            if len(self.timestamps) >= self.limit:
                return False
            self.timestamps.append(now)
            return True


_limiters: dict[int, _RateLimiter] = {}
_limiters_lock = threading.Lock()


def _limiter(limit: int) -> _RateLimiter:
    with _limiters_lock:
        return _limiters.setdefault(limit, _RateLimiter(limit))


def _chat_completions_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    return (
        normalized if normalized.endswith("/chat/completions") else f"{normalized}/chat/completions"
    )


def _content(payload: dict[str, Any]) -> str:
    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise AiGenerationError("AI_RESPONSE_INVALID", "模型响应缺少正文") from exc
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        return "".join(
            str(item.get("text", "")) for item in content if isinstance(item, dict)
        ).strip()
    raise AiGenerationError("AI_RESPONSE_INVALID", "模型响应正文格式不受支持")


def _parse_json(raw: str) -> dict[str, Any]:
    normalized = raw.strip()
    if normalized.startswith("```"):
        normalized = normalized.removeprefix("```json").removeprefix("```")
        normalized = normalized.removesuffix("```").strip()
    try:
        value = json.loads(normalized)
    except json.JSONDecodeError as exc:
        raise AiGenerationError("AI_OUTPUT_NOT_JSON", "模型未返回合法 JSON") from exc
    if not isinstance(value, dict):
        raise AiGenerationError("AI_OUTPUT_SCHEMA_INVALID", "模型输出必须是 JSON 对象")
    return value


class QwenTextProvider:
    provider_name = "qwen"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.model_name = self.settings.llm_structured_model or self.settings.llm_model

    def generate_structured(self, prompt: PromptBundle) -> TextGenerationResult:
        if not self.settings.llm_base_url or not self.settings.llm_api_key.get_secret_value():
            raise AiGenerationError("AI_NOT_CONFIGURED", "真实文本模型尚未配置")
        if not _limiter(self.settings.llm_requests_per_minute).acquire():
            raise AiGenerationError(
                "AI_RATE_LIMITED", "模型请求过于频繁，请稍后重试", retryable=True
            )
        started = time.monotonic()
        total_usage = TokenUsage()
        last_error: AiGenerationError | None = None
        repair_note = ""
        max_attempts = self.settings.llm_max_retries + 1
        attempts_made = 0
        strict_schema_mode = True
        for attempt in range(1, max_attempts + 1):
            attempts_made = attempt
            try:
                if strict_schema_mode:
                    response_format = {
                        "type": "json_schema",
                        "json_schema": {
                            "name": f"{prompt.kind}_output",
                            "strict": True,
                            "schema": prompt.output_schema,
                        },
                    }
                else:
                    response_format = {"type": "json_object"}
                request_payload: dict[str, Any] = {
                    "model": self.model_name,
                    "messages": [
                        {"role": "system", "content": prompt.system_prompt},
                        {"role": "user", "content": prompt.user_prompt + repair_note},
                    ],
                    "temperature": 0.2,
                    "response_format": response_format,
                }
                if not strict_schema_mode:
                    request_payload["max_tokens"] = self.settings.llm_max_output_tokens
                response = httpx.post(
                    _chat_completions_url(self.settings.llm_base_url),
                    headers={
                        "Authorization": f"Bearer {self.settings.llm_api_key.get_secret_value()}",
                        "Content-Type": "application/json",
                    },
                    json=request_payload,
                    timeout=self.settings.llm_timeout_seconds,
                )
                if response.status_code == 429 or response.status_code >= 500:
                    raise AiGenerationError(
                        "AI_UPSTREAM_BUSY",
                        "模型服务暂时繁忙",
                        retryable=True,
                    )
                if response.status_code >= 400:
                    if response.status_code == 400 and strict_schema_mode:
                        strict_schema_mode = False
                        repair_note = (
                            "\n服务端不支持严格 JSON Schema 模式。"
                            "请仍然严格遵守上述 JSON Schema，只输出完整 JSON 对象。"
                        )
                        continue
                    raise AiGenerationError(
                        "AI_UPSTREAM_REJECTED",
                        f"模型服务拒绝请求（HTTP {response.status_code}）",
                    )
                payload = response.json()
                usage_data = payload.get("usage") or {}
                usage = TokenUsage(
                    input_tokens=max(0, int(usage_data.get("prompt_tokens") or 0)),
                    output_tokens=max(0, int(usage_data.get("completion_tokens") or 0)),
                    total_tokens=max(0, int(usage_data.get("total_tokens") or 0)),
                )
                total_usage = TokenUsage(
                    total_usage.input_tokens + usage.input_tokens,
                    total_usage.output_tokens + usage.output_tokens,
                    total_usage.total_tokens + usage.total_tokens,
                )
                raw = _content(payload)
                try:
                    validated = prompt.response_model.model_validate(_parse_json(raw))
                except (AiGenerationError, ValidationError) as exc:
                    if attempt >= max_attempts:
                        raise AiGenerationError(
                            "AI_OUTPUT_SCHEMA_INVALID",
                            "模型输出多次未通过结构校验",
                        ) from exc
                    detail = ""
                    if isinstance(exc, ValidationError):
                        paths = [
                            ".".join(str(part) for part in error["loc"])
                            for error in exc.errors()[:8]
                        ]
                        detail = f"主要错误字段路径：{', '.join(paths)}。"
                    repair_note = (
                        "\n这是结构纠正请求：输出未通过 JSON Schema 校验。"
                        f"{detail}请从头重新生成完整 JSON，严格保持数组嵌套层级，"
                        "不得把子对象提升到父数组，不得省略字段，不要解释原因。"
                    )
                    continue
                return TextGenerationResult(
                    data=validated.model_dump(mode="json"),
                    raw_text=raw,
                    provider_name=self.provider_name,
                    model_name=str(payload.get("model") or self.model_name),
                    usage=total_usage,
                    attempts=attempt,
                    latency_ms=max(0, int((time.monotonic() - started) * 1000)),
                )
            except (httpx.TimeoutException, httpx.NetworkError):
                last_error = AiGenerationError(
                    "AI_NETWORK_ERROR",
                    "模型服务访问超时或网络异常",
                    retryable=True,
                )
            except (json.JSONDecodeError, ValueError):
                last_error = AiGenerationError("AI_RESPONSE_INVALID", "模型服务响应格式异常")
            except AiGenerationError as exc:
                last_error = exc
            if last_error and (not last_error.retryable or attempt >= max_attempts):
                break
            time.sleep(min(2 ** (attempt - 1), 2))
        error = last_error or AiGenerationError("AI_GENERATION_FAILED", "模型生成失败")
        raise AiGenerationError(
            error.code,
            error.message,
            retryable=error.retryable,
            attempts=attempts_made or 1,
            latency_ms=max(0, int((time.monotonic() - started) * 1000)),
            usage=total_usage,
        ) from error


def get_text_provider(settings: Settings | None = None) -> TextProvider:
    settings = settings or get_settings()
    if settings.llm_model.lower() == "mock" or not settings.llm_api_key.get_secret_value():
        return MockTextProvider()
    return QwenTextProvider(settings)
