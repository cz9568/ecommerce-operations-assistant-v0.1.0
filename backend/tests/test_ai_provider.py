import json

from backend.app.config import Settings
from backend.app.integrations.ai.prompts import _sample, build_prompt
from backend.app.integrations.ai.providers import QwenTextProvider


class FakeResponse:
    def __init__(self, status_code: int, payload: dict) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict:
        return self._payload


def _settings() -> Settings:
    return Settings(
        database_password="test-password",
        jwt_secret="x" * 40,
        llm_model="qwen-max",
        llm_structured_model="qwen-plus",
        llm_base_url="https://example.com/compatible-mode/v1",
        llm_api_key="test-key",
        llm_max_retries=2,
        llm_requests_per_minute=1000,
    )


def _success_payload(kind: str) -> dict:
    return {
        "model": "qwen-plus",
        "choices": [{"message": {"content": json.dumps(_sample(kind))}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
    }


def test_qwen_provider_uses_strict_json_schema_without_token_cap(monkeypatch) -> None:
    requests: list[dict] = []

    def fake_post(*_args, **kwargs):
        requests.append(kwargs["json"])
        return FakeResponse(200, _success_payload("main_image"))

    monkeypatch.setattr("backend.app.integrations.ai.providers.httpx.post", fake_post)
    result = QwenTextProvider(_settings()).generate_structured(
        build_prompt("main_image", {"product": {"name": "测试商品"}})
    )

    assert result.model_name == "qwen-plus"
    assert requests[0]["response_format"]["type"] == "json_schema"
    assert requests[0]["response_format"]["json_schema"]["strict"] is True
    assert "max_tokens" not in requests[0]


def test_qwen_provider_falls_back_when_json_schema_mode_is_rejected(monkeypatch) -> None:
    requests: list[dict] = []

    def fake_post(*_args, **kwargs):
        requests.append(kwargs["json"])
        if len(requests) == 1:
            return FakeResponse(400, {"message": "unsupported response format"})
        return FakeResponse(200, _success_payload("diagnosis"))

    monkeypatch.setattr("backend.app.integrations.ai.providers.httpx.post", fake_post)
    result = QwenTextProvider(_settings()).generate_structured(
        build_prompt("diagnosis", {"product": {"name": "测试商品"}})
    )

    assert result.attempts == 2
    assert requests[0]["response_format"]["type"] == "json_schema"
    assert requests[1]["response_format"]["type"] == "json_object"
    assert requests[1]["max_tokens"] == _settings().llm_max_output_tokens
