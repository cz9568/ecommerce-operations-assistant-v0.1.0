import httpx

from backend.app.config import get_settings


def chat_completions_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/chat/completions"):
        return normalized
    return f"{normalized}/chat/completions"


def main() -> None:
    settings = get_settings()
    api_key = settings.llm_api_key.get_secret_value()
    if not settings.llm_base_url:
        raise SystemExit("LLM_BASE_URL 未配置。")
    if not api_key:
        raise SystemExit("LLM_API_KEY 未配置。")

    response = httpx.post(
        chat_completions_url(settings.llm_base_url),
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": settings.llm_model,
            "messages": [{"role": "user", "content": "只回答：OK"}],
            "temperature": 0,
            "max_tokens": 8,
        },
        timeout=settings.llm_timeout_seconds,
    )
    response.raise_for_status()
    payload = response.json()
    answer = payload["choices"][0]["message"]["content"].strip()

    print("QWEN_CONNECTION_OK")
    print(f"model={payload.get('model', settings.llm_model)}")
    print(f"response={answer[:20]}")
    print("api_key=hidden")


if __name__ == "__main__":
    main()
