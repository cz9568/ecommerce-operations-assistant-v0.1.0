import csv
import io
import json
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.api.schemas.performance import PerformanceRecordCreate
from backend.app.api.schemas.products import ProductCreate
from backend.app.api.schemas.skus import SkuCreate
from backend.app.errors import AppError
from backend.app.models.entities import (
    ImportBatch,
    ImportRow,
    InventoryItem,
    InventoryMovement,
    PerformanceRecord,
    Product,
    ProductSku,
    Store,
    User,
)
from backend.app.services.audit import add_audit_log
from backend.app.services.performance import (
    _ensure_period_available,
    _lock_product,
    _validate_references,
    calculate_metrics,
)

MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_ROWS = 1000
IMPORT_TYPES = {"products", "sku_inventory", "performance_records"}

TEMPLATES: dict[str, tuple[list[str], list[str]]] = {
    "products": (
        [
            "store_id",
            "name",
            "category",
            "price",
            "cost",
            "status",
            "target_audience",
            "selling_points",
            "product_url",
            "images",
        ],
        [
            "1",
            "演示保温杯",
            "家居",
            "99.00",
            "42.00",
            "active",
            "通勤人群",
            "长效保温",
            "https://example.com/p/1",
            "https://example.com/a.jpg|https://example.com/b.jpg",
        ],
    ),
    "sku_inventory": (
        [
            "product_id",
            "sku_code",
            "sku_name",
            "specs",
            "price",
            "cost",
            "status",
            "platform_sku_id",
            "stock_qty",
            "locked_qty",
            "warning_threshold",
            "location_text",
        ],
        [
            "1",
            "CUP-WHITE-500",
            "白色 500ml",
            '{"颜色":"白色","容量":"500ml"}',
            "99.00",
            "42.00",
            "active",
            "",
            "120",
            "5",
            "20",
            "A-01",
        ],
    ),
    "performance_records": (
        [
            "product_id",
            "period_start",
            "period_end",
            "impressions",
            "clicks",
            "conversions",
            "spend",
            "revenue",
            "creative_plan_id",
            "generated_asset_id",
            "promotion_link_id",
            "experiment_id",
            "notes",
        ],
        [
            "1",
            "2026-09-01",
            "2026-09-07",
            "10000",
            "500",
            "30",
            "800.00",
            "3600.00",
            "",
            "",
            "",
            "",
            "首周投放",
        ],
    ),
}

FIELD_NOTES: dict[str, dict[str, str]] = {
    "products": {
        "store_id": "必填，现有有效店铺 ID",
        "name": "必填；同一店铺内名称重复会被拒绝",
        "images": "多个 HTTP(S) 图片地址使用 | 分隔",
        "status": "draft、active 或 inactive",
    },
    "sku_inventory": {
        "product_id": "必填，现有商品 ID",
        "sku_code": "同商品内唯一；存在时更新 SKU 并按目标库存生成调整流水",
        "specs": 'JSON 对象，例如 {"颜色":"白色"}',
        "stock_qty": "目标总库存，必须大于等于锁定库存",
        "locked_qty": "目标锁定量，变化会生成 lock/unlock 流水",
    },
    "performance_records": {
        "product_id": "必填，现有商品 ID",
        "period_start": "YYYY-MM-DD",
        "period_end": "YYYY-MM-DD，且有效周期不可重叠",
        "impressions/clicks/conversions": "非负且满足 转化数 ≤ 点击数 ≤ 曝光数",
        "关联 ID": "可空；非空时必须属于同一商品",
    },
}


def template_csv(import_type: str) -> bytes:
    if import_type not in TEMPLATES:
        raise AppError(404, "IMPORT_TEMPLATE_NOT_FOUND", "导入模板不存在")
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(TEMPLATES[import_type][0])
    writer.writerow(TEMPLATES[import_type][1])
    return ("\ufeff" + output.getvalue()).encode("utf-8")


def _batch_response(batch: ImportBatch) -> dict[str, Any]:
    return {
        "id": batch.id,
        "import_type": batch.import_type,
        "batch_status": batch.batch_status,
        "original_filename": batch.original_filename,
        "idempotency_key": batch.idempotency_key,
        "total_rows": batch.total_rows,
        "valid_rows": batch.valid_rows,
        "success_rows": batch.success_rows,
        "failed_rows": batch.failed_rows,
        "created_by": batch.created_by,
        "confirmed_at": batch.confirmed_at,
        "created_at": batch.created_at,
        "updated_at": batch.updated_at,
    }


def _row_response(row: ImportRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "batch_id": row.batch_id,
        "row_number": row.row_number,
        "row_status": row.row_status,
        "raw_data": row.raw_data_json or {},
        "normalized_data": row.normalized_data_json,
        "errors": row.errors_json or [],
        "target_type": row.target_type,
        "target_id": row.target_id,
    }


def _clean_row(row: dict[str, str | None]) -> dict[str, str]:
    return {
        (key or "").strip(): (value or "").strip()
        for key, value in row.items()
        if key is not None and not isinstance(value, list)
    }


def _optional_int(value: str) -> int | None:
    return int(value) if value else None


def _validation_errors(exc: ValidationError) -> list[dict[str, str | None]]:
    return [
        {
            "column": str(item["loc"][-1]) if item.get("loc") else None,
            "code": "INVALID_VALUE",
            "message": str(item["msg"]),
        }
        for item in exc.errors()
    ]


def _validate_product(session: Session, raw: dict[str, str]) -> dict[str, Any]:
    store = session.get(Store, int(raw.get("store_id", "")))
    if store is None or store.status != "active":
        raise AppError(422, "IMPORT_STORE_INVALID", "店铺不存在或已停用")
    images = [item.strip() for item in raw.get("images", "").split("|") if item.strip()]
    payload = ProductCreate.model_validate(
        {
            "store_id": store.id,
            "name": raw.get("name"),
            "category": raw.get("category") or None,
            "price": raw.get("price") or "0",
            "cost": raw.get("cost") or None,
            "status": raw.get("status") or "draft",
            "target_audience": raw.get("target_audience") or None,
            "selling_points": raw.get("selling_points") or None,
            "product_url": raw.get("product_url") or None,
            "images": images,
        }
    )
    duplicate = session.scalar(
        select(Product.id).where(
            Product.store_id == store.id, func.lower(Product.name) == payload.name.lower()
        )
    )
    if duplicate is not None:
        raise AppError(409, "IMPORT_PRODUCT_DUPLICATE", "同一店铺已存在同名商品")
    return payload.model_dump(mode="json")


def _validate_sku_inventory(session: Session, raw: dict[str, str]) -> dict[str, Any]:
    product = session.get(Product, int(raw.get("product_id", "")))
    if product is None:
        raise AppError(422, "IMPORT_PRODUCT_INVALID", "商品不存在")
    store = session.get(Store, product.store_id)
    if product.status == "inactive" or store is None or store.status != "active":
        raise AppError(409, "IMPORT_PRODUCT_INACTIVE", "停用店铺或商品不能导入 SKU 库存")
    try:
        specs = json.loads(raw.get("specs") or "{}")
    except json.JSONDecodeError as exc:
        raise AppError(422, "IMPORT_SPECS_INVALID", "specs 必须是 JSON 对象") from exc
    payload = SkuCreate.model_validate(
        {
            "sku_code": raw.get("sku_code"),
            "sku_name": raw.get("sku_name"),
            "specs": specs,
            "price": raw.get("price") or "0",
            "cost": raw.get("cost") or None,
            "status": raw.get("status") or "active",
            "platform_sku_id": raw.get("platform_sku_id") or None,
        }
    )
    stock = int(raw.get("stock_qty") or "0")
    locked = int(raw.get("locked_qty") or "0")
    warning = int(raw.get("warning_threshold") or "0")
    if min(stock, locked, warning) < 0 or locked > stock:
        raise AppError(422, "IMPORT_INVENTORY_INVALID", "库存必须非负且锁定量不能超过总库存")
    existing_sku = session.scalar(
        select(ProductSku).where(
            ProductSku.product_id == product.id,
            func.lower(ProductSku.sku_code) == payload.sku_code.lower(),
        )
    )
    existing_inventory = (
        session.scalar(select(InventoryItem).where(InventoryItem.sku_id == existing_sku.id))
        if existing_sku is not None
        else None
    )
    before_stock = existing_inventory.stock_qty if existing_inventory is not None else 0
    before_locked = existing_inventory.locked_qty if existing_inventory is not None else 0
    if payload.status == "inactive" and (stock > before_stock or locked > before_locked):
        raise AppError(409, "IMPORT_SKU_INACTIVE", "停用 SKU 不能通过导入增加或锁定库存")
    return {
        "product_id": product.id,
        "sku": payload.model_dump(mode="json"),
        "stock_qty": stock,
        "locked_qty": locked,
        "warning_threshold": warning,
        "location_text": raw.get("location_text") or None,
    }


def _validate_performance(session: Session, raw: dict[str, str]) -> dict[str, Any]:
    product_id = int(raw.get("product_id", ""))
    if session.get(Product, product_id) is None:
        raise AppError(422, "IMPORT_PRODUCT_INVALID", "商品不存在")
    payload = PerformanceRecordCreate.model_validate(
        {
            "period_start": raw.get("period_start"),
            "period_end": raw.get("period_end"),
            "impressions": raw.get("impressions") or "0",
            "clicks": raw.get("clicks") or "0",
            "conversions": raw.get("conversions") or "0",
            "spend": raw.get("spend") or "0",
            "revenue": raw.get("revenue") or "0",
            "creative_plan_id": _optional_int(raw.get("creative_plan_id", "")),
            "generated_asset_id": _optional_int(raw.get("generated_asset_id", "")),
            "promotion_link_id": _optional_int(raw.get("promotion_link_id", "")),
            "experiment_id": _optional_int(raw.get("experiment_id", "")),
            "notes": raw.get("notes") or None,
        }
    )
    _validate_references(session, product_id=product_id, payload=payload)
    _ensure_period_available(
        session,
        product_id=product_id,
        period_start=payload.period_start,
        period_end=payload.period_end,
    )
    return {"product_id": product_id, **payload.model_dump(mode="json")}


def _validate_row(session: Session, import_type: str, raw: dict[str, str]) -> dict[str, Any]:
    validators = {
        "products": _validate_product,
        "sku_inventory": _validate_sku_inventory,
        "performance_records": _validate_performance,
    }
    return validators[import_type](session, raw)


def upload_and_preview(
    session: Session,
    *,
    import_type: str,
    filename: str,
    content: bytes,
    idempotency_key: str,
    actor: User,
    request_id: str | None,
) -> dict[str, Any]:
    if import_type not in IMPORT_TYPES:
        raise AppError(404, "IMPORT_TYPE_NOT_FOUND", "不支持该导入类型")
    existing = session.scalar(
        select(ImportBatch).where(ImportBatch.idempotency_key == idempotency_key)
    )
    if existing is not None:
        if existing.import_type != import_type:
            raise AppError(409, "IMPORT_IDEMPOTENCY_CONFLICT", "幂等键已用于其他导入类型")
        return preview_batch(session, existing.id)
    if not filename.lower().endswith(".csv"):
        raise AppError(422, "IMPORT_FILE_TYPE_INVALID", "首版仅支持 UTF-8 CSV 文件")
    if not content or len(content) > MAX_FILE_BYTES:
        raise AppError(422, "IMPORT_FILE_SIZE_INVALID", "文件不能为空且不能超过 2MB")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise AppError(422, "IMPORT_ENCODING_INVALID", "CSV 必须使用 UTF-8 编码") from exc
    reader = csv.DictReader(io.StringIO(text))
    expected = TEMPLATES[import_type][0]
    actual = [item.strip() for item in (reader.fieldnames or [])]
    missing = [item for item in expected if item not in actual]
    if missing:
        raise AppError(
            422, "IMPORT_HEADER_INVALID", "CSV 缺少必填表头", details={"missing": missing}
        )
    raw_rows = [
        _clean_row(row) for row in reader if any((value or "").strip() for value in row.values())
    ]
    if not raw_rows or len(raw_rows) > MAX_ROWS:
        raise AppError(422, "IMPORT_ROW_COUNT_INVALID", "数据行数必须为 1～1000 行")

    batch = ImportBatch(
        import_type=import_type,
        batch_status="uploaded",
        original_filename=filename[:255],
        idempotency_key=idempotency_key,
        total_rows=len(raw_rows),
        created_by=actor.id,
    )
    session.add(batch)
    session.flush()
    seen: set[tuple[Any, ...]] = set()
    seen_periods: dict[int, list[tuple[str, str]]] = {}
    valid = 0
    for number, raw in enumerate(raw_rows, start=2):
        errors: list[dict[str, Any]] = []
        normalized = None
        try:
            normalized = _validate_row(session, import_type, raw)
            key = (
                (normalized.get("store_id"), str(normalized.get("name", "")).lower())
                if import_type == "products"
                else (
                    normalized["product_id"],
                    normalized.get("sku", {}).get("sku_code", "").lower(),
                )
                if import_type == "sku_inventory"
                else (
                    normalized["product_id"],
                    normalized["period_start"],
                    normalized["period_end"],
                )
            )
            if key in seen:
                raise AppError(422, "IMPORT_DUPLICATE_ROW", "文件内存在重复业务键")
            if import_type == "performance_records":
                product_periods = seen_periods.setdefault(normalized["product_id"], [])
                if any(
                    start <= normalized["period_end"] and end >= normalized["period_start"]
                    for start, end in product_periods
                ):
                    raise AppError(
                        422,
                        "IMPORT_PERIOD_OVERLAP",
                        "文件内同一商品存在重叠经营周期",
                    )
                product_periods.append((normalized["period_start"], normalized["period_end"]))
            seen.add(key)
        except ValidationError as exc:
            errors = _validation_errors(exc)
        except (AppError, ValueError, TypeError) as exc:
            errors = [
                {
                    "column": None,
                    "code": getattr(exc, "code", "INVALID_VALUE"),
                    "message": getattr(exc, "message", str(exc)),
                }
            ]
        row_status = "invalid" if errors else "valid"
        valid += int(row_status == "valid")
        session.add(
            ImportRow(
                batch_id=batch.id,
                row_number=number,
                row_status=row_status,
                raw_data_json=raw,
                normalized_data_json=normalized,
                errors_json=errors,
            )
        )
    batch.valid_rows = valid
    batch.failed_rows = len(raw_rows) - valid
    batch.batch_status = "validated"
    add_audit_log(
        session,
        actor_user_id=actor.id,
        action="import.preview",
        target_type="import_batch",
        target_id=batch.id,
        request_id=request_id,
        detail={"import_type": import_type, "total_rows": len(raw_rows), "valid_rows": valid},
    )
    session.commit()
    return preview_batch(session, batch.id)


def get_batch_or_error(session: Session, batch_id: int) -> ImportBatch:
    batch = session.get(ImportBatch, batch_id)
    if batch is None:
        raise AppError(404, "IMPORT_BATCH_NOT_FOUND", "导入批次不存在")
    return batch


def preview_batch(session: Session, batch_id: int) -> dict[str, Any]:
    batch = get_batch_or_error(session, batch_id)
    rows = session.scalars(
        select(ImportRow).where(ImportRow.batch_id == batch.id).order_by(ImportRow.row_number)
    ).all()
    return {
        "batch": _batch_response(batch),
        "rows": [_row_response(row) for row in rows],
        "field_notes": FIELD_NOTES[batch.import_type],
    }


def list_batches(
    session: Session, *, page: int, page_size: int, import_type: str | None
) -> tuple[list[dict[str, Any]], int]:
    filters = [ImportBatch.import_type == import_type] if import_type else []
    total = session.scalar(select(func.count(ImportBatch.id)).where(*filters)) or 0
    rows = session.scalars(
        select(ImportBatch)
        .where(*filters)
        .order_by(ImportBatch.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return [_batch_response(item) for item in rows], int(total)


def _import_product(session: Session, data: dict[str, Any]) -> tuple[str, int]:
    payload = ProductCreate.model_validate(data)
    store = session.get(Store, payload.store_id)
    if store is None or store.status != "active":
        raise AppError(422, "IMPORT_STORE_INVALID", "店铺不存在或已停用")
    duplicate = session.scalar(
        select(Product.id).where(
            Product.store_id == store.id, func.lower(Product.name) == payload.name.lower()
        )
    )
    if duplicate is not None:
        raise AppError(409, "IMPORT_PRODUCT_DUPLICATE", "同一店铺已存在同名商品")
    product = Product(
        store_id=store.id,
        name=payload.name,
        platform=store.platform,
        category=payload.category,
        price=payload.price,
        cost=payload.cost,
        target_audience=payload.target_audience,
        selling_points=payload.selling_points,
        product_url=payload.product_url,
        images_json=payload.images,
        status=payload.status,
    )
    session.add(product)
    session.flush()
    return "product", product.id


def _movement(
    session: Session,
    *,
    inventory: InventoryItem,
    sku_id: int,
    locked: bool,
    target: int,
    actor_id: int,
    batch_id: int,
) -> None:
    before = inventory.locked_qty if locked else inventory.stock_qty
    delta = target - before
    if delta == 0:
        return
    if locked:
        inventory.locked_qty = target
        movement_type = "lock" if delta > 0 else "unlock"
    else:
        inventory.stock_qty = target
        movement_type = "adjustment"
    inventory.version_no += 1
    session.add(
        InventoryMovement(
            sku_id=sku_id,
            movement_type=movement_type,
            change_qty=delta,
            before_qty=before,
            after_qty=target,
            reason_text="导入中心调整库存",
            reference_type="import_batch",
            reference_id=str(batch_id),
            created_by=actor_id,
        )
    )


def _import_sku_inventory(
    session: Session, data: dict[str, Any], *, actor_id: int, batch_id: int
) -> tuple[str, int]:
    product = session.get(Product, data["product_id"])
    if product is None or product.status == "inactive":
        raise AppError(409, "IMPORT_PRODUCT_INVALID", "商品不存在或已停用")
    payload = SkuCreate.model_validate(data["sku"])
    sku = session.scalar(
        select(ProductSku).where(
            ProductSku.product_id == product.id,
            func.lower(ProductSku.sku_code) == payload.sku_code.lower(),
        )
    )
    if sku is None:
        sku = ProductSku(
            product_id=product.id,
            sku_code=payload.sku_code,
            sku_name=payload.sku_name,
            spec_json=payload.specs,
            price=payload.price,
            cost=payload.cost,
            status=payload.status,
            platform_sku_id=payload.platform_sku_id,
        )
        session.add(sku)
        session.flush()
        inventory = InventoryItem(
            sku_id=sku.id, stock_qty=0, locked_qty=0, warning_threshold=0, version_no=1
        )
        session.add(inventory)
        session.flush()
    else:
        sku.sku_name = payload.sku_name
        sku.spec_json = payload.specs
        sku.price = payload.price
        sku.cost = payload.cost
        sku.status = payload.status
        sku.platform_sku_id = payload.platform_sku_id
        inventory = session.scalar(
            select(InventoryItem).where(InventoryItem.sku_id == sku.id).with_for_update()
        )
        if inventory is None:
            raise AppError(409, "INVENTORY_NOT_INITIALIZED", "SKU 库存记录不存在")
    stock, locked = int(data["stock_qty"]), int(data["locked_qty"])
    if locked > stock:
        raise AppError(422, "IMPORT_INVENTORY_INVALID", "锁定量不能超过总库存")
    if payload.status == "inactive" and (
        stock > inventory.stock_qty or locked > inventory.locked_qty
    ):
        raise AppError(409, "IMPORT_SKU_INACTIVE", "停用 SKU 不能通过导入增加或锁定库存")
    if inventory.locked_qty > stock:
        _movement(
            session,
            inventory=inventory,
            sku_id=sku.id,
            locked=True,
            target=locked,
            actor_id=actor_id,
            batch_id=batch_id,
        )
    _movement(
        session,
        inventory=inventory,
        sku_id=sku.id,
        locked=False,
        target=stock,
        actor_id=actor_id,
        batch_id=batch_id,
    )
    _movement(
        session,
        inventory=inventory,
        sku_id=sku.id,
        locked=True,
        target=locked,
        actor_id=actor_id,
        batch_id=batch_id,
    )
    inventory.warning_threshold = int(data["warning_threshold"])
    inventory.location_text = data.get("location_text")
    return "product_sku", sku.id


def _import_performance(
    session: Session, data: dict[str, Any], *, actor_id: int
) -> tuple[str, int]:
    product_id = int(data.pop("product_id"))
    payload = PerformanceRecordCreate.model_validate(data)
    _lock_product(session, product_id)
    _validate_references(session, product_id=product_id, payload=payload)
    _ensure_period_available(
        session,
        product_id=product_id,
        period_start=payload.period_start,
        period_end=payload.period_end,
    )
    ctr, conversion_rate, roi = calculate_metrics(
        impressions=payload.impressions,
        clicks=payload.clicks,
        conversions=payload.conversions,
        spend=payload.spend,
        revenue=payload.revenue,
    )
    record = PerformanceRecord(
        product_id=product_id,
        **payload.model_dump(),
        ctr=ctr,
        conversion_rate=conversion_rate,
        roi=roi,
        record_status="active",
        version_no=1,
        created_by=actor_id,
        updated_by=actor_id,
    )
    session.add(record)
    session.flush()
    return "performance_record", record.id


def confirm_batch(
    session: Session, *, batch_id: int, actor: User, request_id: str | None
) -> dict[str, Any]:
    batch = session.scalar(select(ImportBatch).where(ImportBatch.id == batch_id).with_for_update())
    if batch is None:
        raise AppError(404, "IMPORT_BATCH_NOT_FOUND", "导入批次不存在")
    if batch.batch_status == "completed":
        return preview_batch(session, batch.id)
    if batch.batch_status != "validated":
        raise AppError(409, "IMPORT_BATCH_STATE_INVALID", "当前批次不能确认导入")
    batch.batch_status = "importing"
    session.flush()
    rows = session.scalars(
        select(ImportRow).where(ImportRow.batch_id == batch.id).order_by(ImportRow.row_number)
    ).all()
    success = 0
    invalid = sum(row.row_status == "invalid" for row in rows)
    handlers = {
        "products": lambda data: _import_product(session, data),
        "sku_inventory": lambda data: _import_sku_inventory(
            session, data, actor_id=actor.id, batch_id=batch.id
        ),
        "performance_records": lambda data: _import_performance(
            session, dict(data), actor_id=actor.id
        ),
    }
    for row in rows:
        if row.row_status != "valid":
            continue
        try:
            with session.begin_nested():
                target_type, target_id = handlers[batch.import_type](row.normalized_data_json or {})
                row.target_type = target_type
                row.target_id = str(target_id)
                row.row_status = "imported"
                row.errors_json = []
                session.flush()
            success += 1
        except (AppError, ValidationError, IntegrityError, ValueError, TypeError) as exc:
            row.row_status = "failed"
            row.errors_json = [
                {
                    "column": None,
                    "code": getattr(exc, "code", "IMPORT_ROW_FAILED"),
                    "message": getattr(exc, "message", str(exc)),
                }
            ]
            invalid += 1
    batch.success_rows = success
    batch.failed_rows = invalid
    batch.batch_status = "completed"
    batch.confirmed_at = datetime.now(UTC)
    add_audit_log(
        session,
        actor_user_id=actor.id,
        action="import.confirm",
        target_type="import_batch",
        target_id=batch.id,
        request_id=request_id,
        detail={"success_rows": success, "failed_rows": invalid},
    )
    session.commit()
    return preview_batch(session, batch.id)


def error_csv(session: Session, batch_id: int) -> bytes:
    batch = get_batch_or_error(session, batch_id)
    rows = session.scalars(
        select(ImportRow)
        .where(ImportRow.batch_id == batch.id, ImportRow.row_status.in_(["invalid", "failed"]))
        .order_by(ImportRow.row_number)
    ).all()
    output = io.StringIO(newline="")
    headers = TEMPLATES[batch.import_type][0]
    writer = csv.writer(output)
    writer.writerow([*headers, "error_columns", "error_codes", "error_messages"])

    def safe_cell(value: object) -> object:
        if isinstance(value, str) and value.startswith(("=", "+", "-", "@")):
            return f"'{value}"
        return value

    for row in rows:
        errors = row.errors_json or []
        writer.writerow(
            [
                *[safe_cell((row.raw_data_json or {}).get(item, "")) for item in headers],
                "|".join(str(item.get("column") or "") for item in errors),
                "|".join(str(item.get("code") or "") for item in errors),
                "|".join(str(item.get("message") or "") for item in errors),
            ]
        )
    return ("\ufeff" + output.getvalue()).encode("utf-8")
