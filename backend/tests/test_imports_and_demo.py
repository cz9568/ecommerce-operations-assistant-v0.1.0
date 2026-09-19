import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.models.entities import (
    ImportBatch,
    InventoryMovement,
    PerformanceRecord,
    Product,
    ProductSku,
    Store,
)
from backend.tests.test_auth_and_users import (
    ADMIN_PASSWORD,
    VIEWER_PASSWORD,
    create_test_user,
    login,
)
from backend.tests.test_products import _create_product, _create_store


async def _headers(
    client: httpx.AsyncClient, session: Session
) -> tuple[dict[str, str], dict[str, str]]:
    create_test_user(session, username="admin", password=ADMIN_PASSWORD, role="admin")
    create_test_user(session, username="viewer", password=VIEWER_PASSWORD, role="viewer")
    return (
        {"Authorization": f"Bearer {await login(client, 'admin', ADMIN_PASSWORD)}"},
        {"Authorization": f"Bearer {await login(client, 'viewer', VIEWER_PASSWORD)}"},
    )


async def test_product_import_preview_partial_confirm_and_idempotency(
    api_client: httpx.AsyncClient, db_session: Session
) -> None:
    admin, viewer = await _headers(api_client, db_session)
    store = await _create_store(api_client, admin, name="导入测试店", external_id="import-store-1")
    template = await api_client.get("/api/v1/imports/templates/products", headers=admin)
    assert template.status_code == 200
    assert template.content.startswith(b"\xef\xbb\xbf")
    assert (
        await api_client.get("/api/v1/imports/templates/products", headers=viewer)
    ).status_code == 403

    before = db_session.scalar(select(func.count(Product.id)))
    content = (
        "store_id,name,category,price,cost,status,target_audience,selling_points,product_url,images\n"
        f"{store['id']},合法商品,家居,88.00,30.00,active,通勤,防漏,https://example.com/p,https://example.com/a.jpg\n"
        f"{store['id']},错误商品,家居,-1,30.00,active,,,,\n"
    ).encode()
    response = await api_client.post(
        "/api/v1/imports/products/upload?filename=products.csv",
        content=content,
        headers={**admin, "X-Idempotency-Key": "products-import-001"},
    )
    assert response.status_code == 200, response.text
    preview = response.json()
    assert preview["batch"]["total_rows"] == 2
    assert preview["batch"]["valid_rows"] == 1
    assert preview["batch"]["failed_rows"] == 1
    assert db_session.scalar(select(func.count(Product.id))) == before

    repeated = await api_client.post(
        "/api/v1/imports/products/upload?filename=products.csv",
        content=content,
        headers={**admin, "X-Idempotency-Key": "products-import-001"},
    )
    assert repeated.json()["batch"]["id"] == preview["batch"]["id"]
    confirmed = await api_client.post(
        f"/api/v1/imports/{preview['batch']['id']}/confirm", headers=admin
    )
    assert confirmed.status_code == 200, confirmed.text
    result = confirmed.json()
    assert result["batch"]["success_rows"] == 1
    assert result["batch"]["failed_rows"] == 1
    assert result["batch"]["total_rows"] == 2
    assert db_session.scalar(select(func.count(Product.id))) == before + 1
    again = await api_client.post(
        f"/api/v1/imports/{preview['batch']['id']}/confirm", headers=admin
    )
    assert again.json()["batch"]["success_rows"] == 1
    errors = await api_client.get(
        f"/api/v1/imports/{preview['batch']['id']}/errors.csv", headers=admin
    )
    assert errors.status_code == 200
    assert "错误商品" in errors.content.decode("utf-8-sig")


async def test_sku_inventory_and_performance_imports(
    api_client: httpx.AsyncClient, db_session: Session
) -> None:
    admin, _viewer = await _headers(api_client, db_session)
    store = await _create_store(api_client, admin, name="业务导入店", external_id="import-store-2")
    product = await _create_product(api_client, admin, store_id=store["id"], name="业务导入商品")
    sku_csv = (
        "product_id,sku_code,sku_name,specs,price,cost,status,platform_sku_id,stock_qty,locked_qty,warning_threshold,location_text\n"
        f'{product["id"]},IMPORT-RED,红色款,"{{""颜色"":""红色""}}",99,40,active,,100,5,20,B-01\n'
    ).encode()
    preview = (
        await api_client.post(
            "/api/v1/imports/sku_inventory/upload?filename=sku.csv",
            content=sku_csv,
            headers={**admin, "X-Idempotency-Key": "sku-import-0001"},
        )
    ).json()
    assert preview["batch"]["valid_rows"] == 1
    confirmed = await api_client.post(
        f"/api/v1/imports/{preview['batch']['id']}/confirm", headers=admin
    )
    assert confirmed.json()["batch"]["success_rows"] == 1
    sku = db_session.scalar(select(ProductSku).where(ProductSku.sku_code == "IMPORT-RED"))
    assert sku is not None
    movements = db_session.scalars(
        select(InventoryMovement).where(InventoryMovement.sku_id == sku.id)
    ).all()
    assert {item.reference_type for item in movements} == {"import_batch"}

    performance_csv = (
        "product_id,period_start,period_end,impressions,clicks,conversions,spend,revenue,creative_plan_id,generated_asset_id,promotion_link_id,experiment_id,notes\n"
        f"{product['id']},2026-09-08,2026-09-14,1000,100,10,200,800,,,,,导入经营数据\n"
    ).encode()
    perf_preview = (
        await api_client.post(
            "/api/v1/imports/performance_records/upload?filename=performance.csv",
            content=performance_csv,
            headers={**admin, "X-Idempotency-Key": "performance-import-001"},
        )
    ).json()
    assert perf_preview["batch"]["valid_rows"] == 1
    perf_result = await api_client.post(
        f"/api/v1/imports/{perf_preview['batch']['id']}/confirm", headers=admin
    )
    assert perf_result.json()["batch"]["success_rows"] == 1
    record = db_session.scalar(select(PerformanceRecord))
    assert record is not None
    assert str(record.ctr) == "0.100000"
    assert str(record.roi) == "4.000000"


async def test_demo_data_is_complete_and_idempotent(
    api_client: httpx.AsyncClient, db_session: Session
) -> None:
    admin, viewer = await _headers(api_client, db_session)
    assert (
        await api_client.post("/api/v1/demo-data/initialize", headers=viewer)
    ).status_code == 403
    first = await api_client.post("/api/v1/demo-data/initialize", headers=admin)
    assert first.status_code == 200, first.text
    payload = first.json()
    assert payload["created"] is True
    assert {
        "competitor",
        "diagnosis",
        "creative_plan",
        "generation_job",
        "asset",
        "promotion_link",
        "ad_recommendation",
        "ad_experiment",
        "performance_record",
        "review_report",
    } <= set(payload["object_ids"])
    counts = (
        db_session.scalar(select(func.count(Store.id))),
        db_session.scalar(select(func.count(Product.id))),
        db_session.scalar(select(func.count(ProductSku.id))),
    )
    second = await api_client.post("/api/v1/demo-data/initialize", headers=admin)
    assert second.status_code == 200
    assert second.json()["created"] is False
    assert counts == (
        db_session.scalar(select(func.count(Store.id))),
        db_session.scalar(select(func.count(Product.id))),
        db_session.scalar(select(func.count(ProductSku.id))),
    )
    assert db_session.scalar(select(func.count(ImportBatch.id))) == 0
