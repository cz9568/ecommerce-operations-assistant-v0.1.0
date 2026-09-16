from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import jwt
from pwdlib import PasswordHash

from backend.app.config import get_settings

password_hasher = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return password_hasher.verify(password, password_hash)


def validate_password_strength(password: str) -> None:
    errors: list[str] = []
    if len(password) < 12:
        errors.append("至少 12 位")
    if not any(character.isupper() for character in password):
        errors.append("至少一个大写字母")
    if not any(character.islower() for character in password):
        errors.append("至少一个小写字母")
    if not any(character.isdigit() for character in password):
        errors.append("至少一个数字")
    if errors:
        raise ValueError("密码必须包含：" + "、".join(errors))


def create_access_token(subject: str, *, extra_claims: dict[str, Any] | None = None) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "jti": uuid4().hex,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(
        payload,
        settings.jwt_secret.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )


def decode_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    return jwt.decode(
        token,
        settings.jwt_secret.get_secret_value(),
        algorithms=[settings.jwt_algorithm],
        options={"require": ["sub", "jti", "iat", "exp"]},
    )
