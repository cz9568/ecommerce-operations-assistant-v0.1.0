from backend.app.config import Settings
from backend.app.integrations.media import DashScopeMediaAdapter, MediaAdapterError


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
        llm_base_url="https://workspace.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
        llm_api_key="test-key",
        generation_provider="dashscope",
        image_model="qwen-image-3.0",
        video_model="wan2.6-t2v",
    )


def test_dashscope_image_submit_and_poll(monkeypatch) -> None:
    requests: list[tuple[str, str, dict]] = []
    responses = [
        FakeResponse(200, {"output": {"task_id": "image-task", "task_status": "PENDING"}}),
        FakeResponse(
            200,
            {
                "output": {
                    "task_status": "SUCCEEDED",
                    "choices": [
                        {"message": {"content": [{"image": "https://example.com/generated.png"}]}}
                    ],
                },
                "usage": {"output_width": 1024, "output_height": 1024},
            },
        ),
    ]

    def fake_request(method, url, **kwargs):
        requests.append((method, url, kwargs))
        return responses.pop(0)

    monkeypatch.setattr("backend.app.integrations.media.providers.httpx.request", fake_request)
    adapter = DashScopeMediaAdapter(_settings())
    snapshot = {
        "plan": {"content": {"generation_prompt": "商品摄影，干净背景"}},
        "parameters": {"size": "1024x1024"},
        "model_name": "qwen-image-3.0",
    }
    submission = adapter.submit(kind="image", input_snapshot=snapshot)
    result = adapter.poll(
        kind="image",
        external_job_id=submission.external_job_id,
        input_snapshot=snapshot,
    )

    assert submission.external_job_id == "image-task"
    assert result.status == "succeeded"
    assert result.result["assets"][0]["width"] == 1024
    assert requests[0][1].endswith("/services/aigc/image-generation/generation")
    assert requests[0][2]["headers"]["X-DashScope-Async"] == "enable"
    assert requests[0][2]["json"]["parameters"]["size"] == "1024*1024"
    assert requests[1][1].endswith("/tasks/image-task")


def test_dashscope_video_submit_and_poll(monkeypatch) -> None:
    responses = [
        FakeResponse(200, {"output": {"task_id": "video-task", "task_status": "PENDING"}}),
        FakeResponse(
            200,
            {
                "output": {
                    "task_status": "SUCCEEDED",
                    "video_url": "https://example.com/generated.mp4",
                },
                "usage": {"output_video_duration": 5, "size": "1280*720"},
            },
        ),
    ]
    request_bodies: list[dict] = []

    def fake_request(_method, _url, **kwargs):
        if "json" in kwargs:
            request_bodies.append(kwargs["json"])
        return responses.pop(0)

    monkeypatch.setattr("backend.app.integrations.media.providers.httpx.request", fake_request)
    adapter = DashScopeMediaAdapter(_settings())
    snapshot = {
        "plan": {
            "content": {
                "title": "收纳演示",
                "hook": "桌面总是很乱？",
                "scenes": [
                    {
                        "order": 1,
                        "visual": "展示杂乱桌面",
                        "voiceover": "先看看使用前",
                    }
                ],
                "call_to_action": "立即查看",
            }
        },
        "parameters": {"size": "1280*720", "duration_seconds": 5},
        "model_name": "wan2.6-t2v",
    }
    submission = adapter.submit(kind="video", input_snapshot=snapshot)
    result = adapter.poll(
        kind="video",
        external_job_id=submission.external_job_id,
        input_snapshot=snapshot,
    )

    assert result.status == "succeeded"
    assert result.result["assets"][0]["duration_seconds"] == 5
    assert request_bodies[0]["model"] == "wan2.6-t2v"
    assert request_bodies[0]["parameters"]["duration"] == 5


def test_dashscope_retryable_error_mapping(monkeypatch) -> None:
    monkeypatch.setattr(
        "backend.app.integrations.media.providers.httpx.request",
        lambda *_args, **_kwargs: FakeResponse(
            503, {"code": "ServiceUnavailable", "message": "busy"}
        ),
    )
    adapter = DashScopeMediaAdapter(_settings())
    try:
        adapter.submit(
            kind="image",
            input_snapshot={
                "plan": {"content": {"generation_prompt": "test"}},
                "parameters": {"size": "1024x1024"},
            },
        )
    except MediaAdapterError as exc:
        assert exc.code == "MEDIA_UPSTREAM_ServiceUnavailable"
        assert exc.retryable is True
    else:
        raise AssertionError("上游 503 应映射为可重试错误")
