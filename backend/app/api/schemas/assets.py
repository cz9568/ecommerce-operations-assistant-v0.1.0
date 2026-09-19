from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

AssetType = Literal["image", "video"]
ReviewStatus = Literal["pending", "approved", "rejected"]
FileStatus = Literal["available", "missing", "invalid"]


class AssetUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_lock_version: int = Field(ge=1)
    usage_scene: str | None = Field(default=None, max_length=255)
    score: Decimal | None = Field(default=None, ge=0, le=5, decimal_places=2)
    tags: list[str] | None = Field(default=None, max_length=20)
    remark: str | None = Field(default=None, max_length=5000)

    @field_validator("usage_scene", "remark")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        normalized = value.strip() if value else None
        return normalized or None

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        normalized: list[str] = []
        seen: set[str] = set()
        for raw_tag in value:
            tag = raw_tag.strip()
            if not tag:
                continue
            if len(tag) > 32:
                raise ValueError("单个标签不能超过 32 个字符")
            key = tag.casefold()
            if key not in seen:
                seen.add(key)
                normalized.append(tag)
        return normalized

    @model_validator(mode="after")
    def require_change(self) -> "AssetUpdate":
        if not (set(self.model_fields_set) - {"expected_lock_version"}):
            raise ValueError("至少提供一个需要更新的字段")
        return self


class AssetReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_lock_version: int = Field(ge=1)
    review_status: ReviewStatus
    remark: str | None = Field(default=None, max_length=5000)

    @field_validator("remark")
    @classmethod
    def normalize_remark(cls, value: str | None) -> str | None:
        normalized = value.strip() if value else None
        return normalized or None


class AssetResponse(BaseModel):
    id: int
    product_id: int
    creative_plan_id: int
    generation_job_id: int | None
    source_asset_index: int
    asset_type: AssetType
    storage_key: str
    content_url: str
    mime_type: str | None
    file_size_bytes: int
    checksum_sha256: str | None
    file_status: FileStatus
    model_name: str | None
    width: int | None
    height: int | None
    duration_sec: Decimal | None
    review_status: ReviewStatus
    reviewed_by: int | None
    reviewed_at: datetime | None
    version_no: int
    lock_version: int
    usage_scene: str | None
    score: Decimal | None
    tags: list[str]
    remark: str | None
    synced_at: datetime | None
    created_at: datetime
    updated_at: datetime
