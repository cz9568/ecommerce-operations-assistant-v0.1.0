from sqlalchemy.orm import Session

from backend.app.models.entities import AiUsageLog


def add_ai_usage_log(
    session: Session,
    *,
    request_id: str | None,
    scene: str,
    provider_name: str,
    model_name: str,
    prompt_version: str,
    status: str,
    input_tokens: int,
    output_tokens: int,
    total_tokens: int,
    latency_ms: int,
    attempts: int,
    error_code: str | None,
    actor_id: int,
    target_type: str,
    target_id: str,
) -> None:
    session.add(
        AiUsageLog(
            request_id=request_id,
            scene=scene,
            provider_name=provider_name,
            model_name=model_name,
            prompt_version=prompt_version,
            status=status,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            latency_ms=latency_ms,
            attempts=attempts,
            error_code=error_code,
            actor_user_id=actor_id,
            target_type=target_type,
            target_id=target_id,
        )
    )
