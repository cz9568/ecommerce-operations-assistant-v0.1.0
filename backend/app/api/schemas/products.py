from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    field_validator,
    model_validator,
)

from backend.app.api.schemas.stores import StorePlatform

ProductStatus = Literal["draft", "active", "inactive"]
MappingStatus = Literal["active", "inactive", "invalid"]
Money = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]
_http_url_adapter = TypeAdapter(AnyHttpUrl)


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


def _http_url(value: str | None) -> str | None:
    value = _strip_optional(value)
    if value is None:
        return None
    return str(_http_url_adapter.validate_python(value))


def _image_urls(values: list[str]) -> list[str]:
    normalized: list[str] = []
    for value in values:
        url = _http_url(value)
        if url is None:
            raise ValueError("图片地址不能为空")
        if url not in normalized:
            normalized.append(url)
    return normalized


class ProductCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    store_id: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=255)
    category: str | None = Field(default=None, max_length=120)
    price: Money = Decimal("0")
    cost: Money | None = None
    target_audience: str | None = Field(default=None, max_length=10000)
    selling_points: str | None = Field(default=None, max_length=10000)
    product_url: str | None = Field(default=None, max_length=2048)
    images: list[str] = Field(default_factory=list, max_length=20)
    status: ProductStatus = "draft"

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        return _strip_required(value)

    @field_validator("category", "target_audience", "selling_points")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        return _strip_optional(value)

    @field_validator("product_url")
    @classmethod
    def validate_product_url(cls, value: str | None) -> str | None:
        return _http_url(value)

    @field_validator("images")
    @classmethod
    def validate_images(cls, value: list[str]) -> list[str]:
        return _image_urls(value)


class ProductUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=255)
    category: str | None = Field(default=None, max_length=120)
    price: Money | None = None
    cost: Money | None = None
    target_audience: str | None = Field(default=None, max_length=10000)
    selling_points: str | None = Field(default=None, max_length=10000)
    product_url: str | None = Field(default=None, max_length=2048)
    images: list[str] | None = Field(default=None, max_length=20)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("商品名称不能设为空")
        return _strip_required(value)

    @field_validator("price")
    @classmethod
    def reject_null_price(cls, value: Decimal | None) -> Decimal:
        if value is None:
            raise ValueError("商品价格不能设为空")
        return value

    @field_validator("category", "target_audience", "selling_points")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        return _strip_optional(value)

    @field_validator("product_url")
    @classmethod
    def validate_product_url(cls, value: str | None) -> str | None:
        return _http_url(value)

    @field_validator("images")
    @classmethod
    def validate_images(cls, value: list[str] | None) -> list[str]:
        if value is None:
            raise ValueError("商品图片不能设为空，请使用空数组清空")
        return _image_urls(value)

    @model_validator(mode="after")
    def contains_change(self) -> "ProductUpdate":
        if not self.model_fields_set:
            raise ValueError("至少需要提供一个待更新字段")
        return self


class ProductStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["active", "inactive"]


class ProductResponse(BaseModel):
    id: int
    store_id: int
    store_name: str
    name: str
    platform: StorePlatform
    category: str | None
    price: Decimal
    cost: Decimal | None
    target_audience: str | None
    selling_points: str | None
    product_url: str | None
    images: list[str]
    status: ProductStatus
    mapping_count: int = Field(ge=0)
    last_diagnosis_at: datetime | None
    last_review_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ProductMappingCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    platform_product_id: str = Field(min_length=1, max_length=128)
    platform_sku_id: str = Field(default="", max_length=128)
    mapping_status: MappingStatus = "active"

    @field_validator("platform_product_id")
    @classmethod
    def strip_product_id(cls, value: str) -> str:
        return _strip_required(value)

    @field_validator("platform_sku_id")
    @classmethod
    def strip_sku_id(cls, value: str) -> str:
        return value.strip()


class ProductMappingUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    platform_product_id: str | None = Field(default=None, min_length=1, max_length=128)
    platform_sku_id: str | None = Field(default=None, max_length=128)
    mapping_status: MappingStatus | None = None

    @field_validator("platform_product_id")
    @classmethod
    def strip_product_id(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("平台商品编号不能设为空")
        return _strip_required(value)

    @field_validator("platform_sku_id")
    @classmethod
    def strip_sku_id(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("平台 SKU 编号不能设为空，请使用空字符串清空")
        return value.strip()

    @field_validator("mapping_status")
    @classmethod
    def reject_null_status(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("映射状态不能设为空")
        return value

    @model_validator(mode="after")
    def contains_change(self) -> "ProductMappingUpdate":
        if not self.model_fields_set:
            raise ValueError("至少需要提供一个待更新字段")
        return self


class ProductMappingResponse(BaseModel):
    id: int
    store_id: int
    product_id: int
    platform: StorePlatform
    platform_product_id: str
    platform_sku_id: str
    mapping_status: MappingStatus
    created_at: datetime
    updated_at: datetime
