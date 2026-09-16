from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.app.security import validate_password_strength

UserRole = Literal["admin", "operator", "viewer"]
UserStatus = Literal["active", "inactive"]


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    display_name: str
    role: UserRole
    status: UserStatus
    last_login_at: datetime | None
    created_at: datetime
    updated_at: datetime


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    display_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=12, max_length=256)
    role: UserRole = "viewer"
    status: UserStatus = "active"

    @field_validator("password")
    @classmethod
    def password_is_strong(cls, value: str) -> str:
        validate_password_strength(value)
        return value


class UserUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    password: str | None = Field(default=None, min_length=12, max_length=256)
    role: UserRole | None = None
    status: UserStatus | None = None

    @field_validator("password")
    @classmethod
    def password_is_strong(cls, value: str | None) -> str | None:
        if value is not None:
            validate_password_strength(value)
        return value

    @model_validator(mode="after")
    def contains_change(self) -> "UserUpdate":
        if not self.model_fields_set:
            raise ValueError("至少需要提供一个待更新字段")
        return self
