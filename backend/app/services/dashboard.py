from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.models.entities import (
    GeneratedAsset,
    GenerationJob,
    InventoryItem,
    Product,
    ProductSku,
    ReviewReport,
    Store,
)
from backend.app.services.demo_data import DEMO_MARKER


def _subqueries():
    low_stock = (
        select(
            Product.id.label("product_id"),
            Product.store_id.label("store_id"),
            func.count(InventoryItem.id).label("count"),
        )
        .join(ProductSku, ProductSku.product_id == Product.id)
        .join(InventoryItem, InventoryItem.sku_id == ProductSku.id)
        .where(
            Product.status == "active",
            ProductSku.status == "active",
            InventoryItem.stock_qty - InventoryItem.locked_qty <= InventoryItem.warning_threshold,
        )
        .group_by(Product.id, Product.store_id)
        .subquery()
    )
    active_jobs = (
        select(
            GenerationJob.product_id.label("product_id"),
            func.count(GenerationJob.id).label("count"),
        )
        .where(GenerationJob.job_status.in_(["pending", "running"]))
        .group_by(GenerationJob.product_id)
        .subquery()
    )
    latest_review = (
        select(
            ReviewReport.product_id.label("product_id"),
            func.max(ReviewReport.created_at).label("created_at"),
        )
        .group_by(ReviewReport.product_id)
        .subquery()
    )
    latest_job_id = (
        select(
            GenerationJob.product_id.label("product_id"),
            func.max(GenerationJob.id).label("job_id"),
        )
        .group_by(GenerationJob.product_id)
        .subquery()
    )
    return low_stock, active_jobs, latest_review, latest_job_id


def dashboard_summary(session: Session, *, platform: str | None) -> dict[str, Any]:
    store_filter = [Store.platform == platform] if platform else []
    available_platforms = list(
        session.scalars(select(Store.platform).distinct().order_by(Store.platform)).all()
    )
    low_stock, active_jobs, latest_review, latest_job_id = _subqueries()

    store_rows = session.execute(
        select(
            Store,
            func.count(func.distinct(Product.id)).label("product_count"),
            func.coalesce(func.sum(func.coalesce(low_stock.c.count, 0)), 0).label(
                "low_stock_count"
            ),
            func.coalesce(func.sum(func.coalesce(active_jobs.c.count, 0)), 0).label(
                "active_job_count"
            ),
            func.max(latest_review.c.created_at).label("latest_review_at"),
        )
        .outerjoin(Product, Product.store_id == Store.id)
        .outerjoin(low_stock, low_stock.c.product_id == Product.id)
        .outerjoin(active_jobs, active_jobs.c.product_id == Product.id)
        .outerjoin(latest_review, latest_review.c.product_id == Product.id)
        .where(*store_filter)
        .group_by(Store.id)
        .order_by(Store.status.asc(), Store.id.asc())
    ).all()
    product_rows = session.execute(
        select(
            Product,
            Store.store_name,
            func.coalesce(low_stock.c.count, 0).label("low_stock_count"),
            GenerationJob.job_status.label("latest_job_status"),
            latest_review.c.created_at.label("latest_review_at"),
        )
        .join(Store, Store.id == Product.store_id)
        .outerjoin(low_stock, low_stock.c.product_id == Product.id)
        .outerjoin(latest_job_id, latest_job_id.c.product_id == Product.id)
        .outerjoin(GenerationJob, GenerationJob.id == latest_job_id.c.job_id)
        .outerjoin(latest_review, latest_review.c.product_id == Product.id)
        .where(*store_filter)
        .order_by(Product.updated_at.desc(), Product.id.desc())
        .limit(12)
    ).all()
    low_rows = session.execute(
        select(InventoryItem, ProductSku, Product)
        .join(ProductSku, ProductSku.id == InventoryItem.sku_id)
        .join(Product, Product.id == ProductSku.product_id)
        .join(Store, Store.id == Product.store_id)
        .where(
            *store_filter,
            Store.status == "active",
            Product.status == "active",
            ProductSku.status == "active",
            InventoryItem.stock_qty - InventoryItem.locked_qty <= InventoryItem.warning_threshold,
        )
        .order_by(
            (InventoryItem.stock_qty - InventoryItem.locked_qty).asc(),
            InventoryItem.id.asc(),
        )
        .limit(10)
    ).all()
    job_rows = session.execute(
        select(GenerationJob, Product.name.label("product_name"))
        .join(Product, Product.id == GenerationJob.product_id)
        .join(Store, Store.id == Product.store_id)
        .where(*store_filter)
        .order_by(GenerationJob.created_at.desc(), GenerationJob.id.desc())
        .limit(8)
    ).all()
    review_rows = session.execute(
        select(ReviewReport, Product.name.label("product_name"))
        .join(Product, Product.id == ReviewReport.product_id)
        .join(Store, Store.id == Product.store_id)
        .where(*store_filter)
        .order_by(ReviewReport.created_at.desc(), ReviewReport.id.desc())
        .limit(8)
    ).all()
    product_ids = select(Product.id).join(Store, Store.id == Product.store_id).where(*store_filter)
    metrics = {
        "store_count": len(store_rows),
        "product_count": session.scalar(select(func.count()).select_from(product_ids.subquery()))
        or 0,
        "low_stock_count": sum(int(row.low_stock_count) for row in store_rows),
        "active_job_count": session.scalar(
            select(func.count(GenerationJob.id)).where(
                GenerationJob.product_id.in_(product_ids),
                GenerationJob.job_status.in_(["pending", "running"]),
            )
        )
        or 0,
        "pending_asset_count": session.scalar(
            select(func.count(GeneratedAsset.id)).where(
                GeneratedAsset.product_id.in_(product_ids),
                GeneratedAsset.review_status == "pending",
            )
        )
        or 0,
        "review_report_count": session.scalar(
            select(func.count(ReviewReport.id)).where(ReviewReport.product_id.in_(product_ids))
        )
        or 0,
    }
    return {
        "platform": platform,
        "available_platforms": available_platforms,
        "metrics": metrics,
        "stores": [
            {
                "id": row.Store.id,
                "store_name": row.Store.store_name,
                "platform": row.Store.platform,
                "status": row.Store.status,
                "product_count": int(row.product_count),
                "low_stock_count": int(row.low_stock_count),
                "active_job_count": int(row.active_job_count),
                "latest_review_at": row.latest_review_at,
            }
            for row in store_rows
        ],
        "products": [
            {
                "id": row.Product.id,
                "name": row.Product.name,
                "store_id": row.Product.store_id,
                "store_name": row.store_name,
                "platform": row.Product.platform,
                "status": row.Product.status,
                "low_stock_count": int(row.low_stock_count),
                "latest_job_status": row.latest_job_status,
                "latest_review_at": row.latest_review_at,
            }
            for row in product_rows
        ],
        "low_stock": [
            {
                "product_id": row.Product.id,
                "product_name": row.Product.name,
                "sku_id": row.ProductSku.id,
                "sku_code": row.ProductSku.sku_code,
                "available_qty": row.InventoryItem.stock_qty - row.InventoryItem.locked_qty,
                "warning_threshold": row.InventoryItem.warning_threshold,
            }
            for row in low_rows
        ],
        "recent_jobs": [
            {
                "id": row.GenerationJob.id,
                "product_id": row.GenerationJob.product_id,
                "product_name": row.product_name,
                "job_kind": row.GenerationJob.job_kind,
                "job_status": row.GenerationJob.job_status,
                "progress_percent": row.GenerationJob.progress_percent,
                "created_at": row.GenerationJob.created_at,
            }
            for row in job_rows
        ],
        "recent_reviews": [
            {
                "id": row.ReviewReport.id,
                "product_id": row.ReviewReport.product_id,
                "product_name": row.product_name,
                "period_start": row.ReviewReport.period_start,
                "period_end": row.ReviewReport.period_end,
                "roi": (row.ReviewReport.input_snapshot_json or {}).get("aggregate", {}).get("roi"),
                "created_at": row.ReviewReport.created_at,
            }
            for row in review_rows
        ],
        "has_demo_data": session.scalar(
            select(Store.id).where(Store.external_store_id == DEMO_MARKER).limit(1)
        )
        is not None,
    }
