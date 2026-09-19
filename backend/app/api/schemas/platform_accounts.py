from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.app.api.schemas.stores import StorePlatform

AuthorizationStatus = Literal[
    "unconfigured",
    "pending",
    "authorized",
    "expired",
    "revoked",
    "failed",
]


def _strip_required(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError("字段不能为空")
    return stripped


def _strip_optional(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


class PlatformAccountCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_name: str = Field(min_length=1, max_length=128)
    remark: str | None = Field(default=None, max_length=2000)

    @field_validator("account_name")
    @classmethod
    def strip_account_name(cls, value: str) -> str:
        return _strip_required(value)

    @field_validator("remark")
    @classmethod
    def strip_remark(cls, value: str | None) -> str | None:
        return _strip_optional(value)


class PlatformAccountUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_name: str | None = Field(default=None, min_length=1, max_length=128)
    remark: str | None = Field(default=None, max_length=2000)

    @field_validator("account_name")
    @classmethod
    def strip_account_name(cls, value: str | None) -> str | None:
        if value is None:
            raise ValueError("账号标识不能设为空")
        return _strip_required(value)

    @field_validator("remark")
    @classmethod
    def strip_remark(cls, value: str | None) -> str | None:
        return _strip_optional(value)

    @model_validator(mode="after")
    def contains_change(self) -> "PlatformAccountUpdate":
        if not self.model_fields_set:
            raise ValueError("至少需要提供一个待更新字段")
        return self


class PublicAuthMeta(BaseModel):
    seller_id: str | None = None
    scopes: list[str] = Field(default_factory=list)
    expires_at: datetime | None = None
    last_authorized_at: datetime | None = None
    last_error_code: str | None = None


class PlatformAccountResponse(BaseModel):
    id: int
    store_id: int
    platform: StorePlatform
    account_name_masked: str
    auth_status: AuthorizationStatus
    auth_meta: PublicAuthMeta
    remark: str | None
    created_at: datetime
    updated_at: datetime


class AuthorizationStartResponse(BaseModel):
    account_id: int
    auth_status: Literal["pending"]
    state: str
    authorization_url: str | None = None
    callback_path: str
    message: str


class AuthorizationCallback(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: str = Field(min_length=32, max_length=256)
    result: Literal["authorized", "failed", "expired"]
    seller_id: str | None = Field(default=None, max_length=128)
    scopes: list[str] = Field(default_factory=list, max_length=50)
    expires_at: datetime | None = None
    error_code: str | None = Field(default=None, max_length=100)

    @field_validator("seller_id", "error_code")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        return _strip_optional(value)

    @field_validator("scopes")
    @classmethod
    def validate_scopes(cls, value: list[str]) -> list[str]:
        normalized = []
        for scope in value:
            stripped = scope.strip()
            if not stripped or len(stripped) > 100:
                raise ValueError("权限范围必须是 1～100 个字符")
            if stripped not in normalized:
                normalized.append(stripped)
        return normalized
