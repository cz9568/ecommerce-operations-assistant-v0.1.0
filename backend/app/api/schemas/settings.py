from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SettingGroup = Literal["model", "system", "queue"]
ApplyMode = Literal["immediate", "new_requests", "worker_restart", "service_restart"]


class SettingItemResponse(BaseModel):
    key: str
    group: SettingGroup
    label: str
    description: str
    value_type: Literal["string", "integer", "boolean", "decimal", "json"]
    value: Any | None
    sensitive: bool
    configured: bool
    source: Literal["environment", "database"]
    apply_mode: ApplyMode
    updated_at: datetime | None


class SettingsResponse(BaseModel):
    groups: dict[SettingGroup, list[SettingItemResponse]]


class SettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    values: dict[str, Any] = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def require_values(self) -> "SettingsUpdate":
        if not self.values:
            raise ValueError("至少提供一个配置项")
        return self
