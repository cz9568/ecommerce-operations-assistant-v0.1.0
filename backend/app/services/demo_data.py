from datetime import UTC, date, datetime
from decimal import Decimal
from hashlib import sha256
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.integrations.storage import get_storage_adapter, mock_media_bytes
from backend.app.models.entities import (
    AdExperiment,
    AdRecommendation,
    Competitor,
    CreativePlan,
    CreativePlanRevision,
    GeneratedAsset,
    GenerationJob,
    GenerationJobEvent,
    InventoryItem,
    InventoryMovement,
    PerformanceRecord,
    PlatformAccount,
    PlatformProductMapping,
    Product,
    ProductDiagnosis,
    ProductSku,
    PromotionLink,
    ReviewReport,
    ReviewReportRevision,
    Store,
    User,
)
from backend.app.services.audit import add_audit_log
from backend.app.services.performance import calculate_metrics

DEMO_MARKER = "ecommerce-ops-demo-v1"


def _response(session: Session, store: Store, *, created: bool) -> dict[str, Any]:
    product = session.scalar(select(Product).where(Product.store_id == store.id))
    assert product is not None
    sku = session.scalar(select(ProductSku).where(ProductSku.product_id == product.id))
    assert sku is not None
    ids: dict[str, int] = {}
    for label, model in (
        ("competitor", Competitor),
        ("diagnosis", ProductDiagnosis),
        ("creative_plan", CreativePlan),
        ("generation_job", GenerationJob),
        ("asset", GeneratedAsset),
        ("promotion_link", PromotionLink),
        ("ad_recommendation", AdRecommendation),
        ("ad_experiment", AdExperiment),
        ("performance_record", PerformanceRecord),
        ("review_report", ReviewReport),
    ):
        object_id = session.scalar(
            select(model.id).where(model.product_id == product.id).order_by(model.id.asc()).limit(1)
        )
        if object_id is not None:
            ids[label] = int(object_id)
    return {
        "created": created,
        "marker": DEMO_MARKER,
        "store_id": store.id,
        "product_id": product.id,
        "sku_id": sku.id,
        "object_ids": ids,
        "message": "演示数据已创建，可从店铺或商品详情体验完整闭环"
        if created
        else "演示数据已存在，本次未重复创建",
    }


def initialize_demo_data(
    session: Session,
    *,
    actor: User,
    request_id: str | None,
    rebuild: bool,
) -> dict[str, Any]:
    existing = session.scalar(
        select(Store).where(Store.platform == "taobao", Store.external_store_id == DEMO_MARKER)
    )
    if existing is not None and not rebuild:
        return _response(session, existing, created=False)
    if existing is not None:
        existing.store_name = "【演示】曜石生活旗舰店"
        existing.status = "active"
        existing.owner_user_id = actor.id
        existing.owner_name = actor.display_name
        session.commit()
        return _response(session, existing, created=False)

    now = datetime.now(UTC)
    store = Store(
        store_name="【演示】曜石生活旗舰店",
        platform="taobao",
        external_store_id=DEMO_MARKER,
        owner_user_id=actor.id,
        owner_name=actor.display_name,
        status="active",
        remark="M10 幂等演示数据；以固定 external_store_id 识别",
    )
    session.add(store)
    session.flush()
    session.add(
        PlatformAccount(
            store_id=store.id,
            platform="taobao",
            account_name="demo_seller",
            auth_status="authorized",
            auth_meta_json={"seller_id": "DEMO-SELLER", "scope": ["read_demo"]},
            remark="演示授权，不包含真实凭据",
        )
    )
    product = Product(
        store_id=store.id,
        name="【演示】轻量恒温随行杯",
        platform="taobao",
        category="家居/水具",
        price=Decimal("129.00"),
        cost=Decimal("48.00"),
        target_audience="20～35 岁通勤、健身和短途出行人群",
        selling_points="12 小时保温、轻量防漏、单手开启、食品级内胆",
        product_url="https://example.com/demo/tumbler",
        images_json=["https://example.com/demo/tumbler-cover.png"],
        status="active",
    )
    session.add(product)
    session.flush()
    session.add(
        PlatformProductMapping(
            store_id=store.id,
            product_id=product.id,
            platform="taobao",
            platform_product_id="DEMO-PRODUCT-001",
            platform_sku_id="",
            mapping_status="active",
            raw_payload_json={"source": "demo"},
        )
    )
    sku = ProductSku(
        product_id=product.id,
        sku_code="DEMO-WHITE-500",
        sku_name="月光白 500ml",
        spec_json={"颜色": "月光白", "容量": "500ml"},
        price=Decimal("129.00"),
        cost=Decimal("48.00"),
        status="active",
        platform_sku_id="DEMO-SKU-001",
    )
    session.add(sku)
    session.flush()
    inventory = InventoryItem(
        sku_id=sku.id,
        stock_qty=86,
        locked_qty=6,
        warning_threshold=20,
        location_text="DEMO-A-01",
        version_no=1,
    )
    session.add(inventory)
    session.add(
        InventoryMovement(
            sku_id=sku.id,
            movement_type="inbound",
            change_qty=86,
            before_qty=0,
            after_qty=86,
            reason_text="演示数据初始化入库",
            reference_type="demo_seed",
            reference_id=DEMO_MARKER,
            created_by=actor.id,
        )
    )
    competitor = Competitor(
        product_id=product.id,
        name="【演示竞品】城市保温杯",
        platform="taobao",
        url="https://example.com/demo/competitor",
        price=Decimal("139.00"),
        sales_hint="月销 2000+（演示）",
        title="轻量不锈钢保温杯",
        selling_points="保温、防漏、多色",
        review_keywords="颜值高、保温好；杯盖清洁不便",
        status="active",
        field_sources_json={"price": "manual", "selling_points": "manual"},
    )
    session.add(competitor)
    session.flush()
    diagnosis = ProductDiagnosis(
        product_id=product.id,
        source_type="ai",
        positioning="中价格带的轻量通勤保温杯",
        price_band="高于入门款，低于专业户外杯",
        audience_insights="重视颜值、重量与防漏体验",
        pain_points="传统保温杯笨重、杯盖难清洗",
        selling_point_analysis="用重量与保温时长形成可量化证据",
        risks="演示数据不代表真实市场结论",
        recommendations="突出轻量与单手开启，验证白领通勤场景",
        raw_output="demo",
        input_snapshot_json={"marker": DEMO_MARKER, "competitor_ids": [competitor.id]},
        model_name="mock",
        provider_name="mock",
        prompt_version="diagnosis-v1",
        schema_version="diagnosis-v1",
        generated_by=actor.id,
        version_no=1,
    )
    session.add(diagnosis)
    session.flush()
    plan = CreativePlan(
        product_id=product.id,
        plan_type="main_image",
        generation_batch_id="demo-main-image",
        title="轻量通勤主视觉",
        content_json={
            "headline": "轻装出发，温度刚好",
            "visual": "晨间通勤与单手持杯",
            "composition": "产品居中，卖点环绕",
        },
        rationale_text="突出重量、保温与通勤场景",
        status="selected",
        raw_output="demo",
        input_snapshot_json={"diagnosis_id": diagnosis.id},
        provider_name="mock",
        model_name="mock",
        prompt_version="main-image-v1",
        schema_version="main-image-v1",
        generated_by=actor.id,
        version_no=1,
    )
    session.add(plan)
    session.flush()
    session.add(
        CreativePlanRevision(
            creative_plan_id=plan.id,
            version_no=1,
            title=plan.title,
            content_json=plan.content_json,
            rationale_text=plan.rationale_text,
            status=plan.status,
            changed_by=actor.id,
        )
    )
    job = GenerationJob(
        product_id=product.id,
        creative_plan_id=plan.id,
        creative_plan_version_no=1,
        job_kind="image",
        job_status="succeeded",
        idempotency_key=f"{DEMO_MARKER}-image",
        provider_name="mock",
        input_snapshot_json={"plan_id": plan.id, "version_no": 1},
        requested_by=actor.id,
        attempts=1,
        max_attempts=3,
        progress_percent=100,
        result_json={"assets": [{"width": 1024, "height": 1024}]},
        started_at=now,
        finished_at=now,
        version_no=2,
    )
    session.add(job)
    session.flush()
    session.add(
        GenerationJobEvent(
            job_id=job.id,
            event_type="succeeded",
            event_message="演示图片生成完成",
            event_data_json={"provider": "mock"},
        )
    )
    media = mock_media_bytes("image")
    storage_key = f"demo/{DEMO_MARKER}/main-image.png"
    get_storage_adapter().put_bytes(storage_key, media.content)
    asset = GeneratedAsset(
        product_id=product.id,
        creative_plan_id=plan.id,
        generation_job_id=job.id,
        source_asset_index=0,
        asset_type="image",
        storage_key=storage_key,
        mime_type=media.mime_type,
        file_size_bytes=len(media.content),
        checksum_sha256=sha256(media.content).hexdigest(),
        file_status="available",
        model_name="mock",
        width=1024,
        height=1024,
        review_status="approved",
        reviewed_by=actor.id,
        reviewed_at=now,
        version_no=1,
        lock_version=1,
        usage_scene="商品主图",
        score=Decimal("4.50"),
        tags_json=["演示", "通勤"],
        remark="演示素材",
        synced_at=now,
    )
    session.add(asset)
    session.flush()
    rejected_key = f"demo/{DEMO_MARKER}/rejected-image.png"
    get_storage_adapter().put_bytes(rejected_key, media.content)
    session.add(
        GeneratedAsset(
            product_id=product.id,
            creative_plan_id=plan.id,
            source_asset_index=1,
            asset_type="image",
            storage_key=rejected_key,
            mime_type=media.mime_type,
            file_size_bytes=len(media.content),
            checksum_sha256=sha256(media.content).hexdigest(),
            file_status="available",
            model_name="mock",
            width=1024,
            height=1024,
            review_status="rejected",
            reviewed_by=actor.id,
            reviewed_at=now,
            version_no=2,
            lock_version=1,
            usage_scene="备选主图",
            tags_json=["演示", "已驳回"],
            remark="用于演示不同素材审核状态",
            synced_at=now,
        )
    )
    session.add(
        GenerationJob(
            product_id=product.id,
            creative_plan_id=plan.id,
            creative_plan_version_no=1,
            job_kind="image",
            job_status="failed",
            idempotency_key=f"{DEMO_MARKER}-failed-image",
            provider_name="mock",
            input_snapshot_json={"plan_id": plan.id, "demo_state": "failed"},
            requested_by=actor.id,
            attempts=3,
            max_attempts=3,
            progress_percent=65,
            error_code="DEMO_PROVIDER_ERROR",
            error_message="演示用稳定错误，不会调用真实模型",
            started_at=now,
            finished_at=now,
            version_no=3,
        )
    )
    link = PromotionLink(
        product_id=product.id,
        link_name="演示内容种草链接",
        target_url=product.product_url,
        tracking_code="demo-tumbler-v1",
        utm_json={"source": "demo", "medium": "content", "campaign": "m10"},
        status="active",
        click_count=128,
        scene_text="内容平台种草",
        lock_version=1,
    )
    session.add(link)
    session.flush()
    recommendation = AdRecommendation(
        product_id=product.id,
        summary_text="以轻量通勤为核心，先小预算验证点击与转化",
        objective_text="验证主图与通勤人群匹配度",
        audience_segments_json=[{"name": "都市通勤人群", "reason": "高频携带需求"}],
        budget_plan_json={"daily": 200, "days": 7},
        creative_tests_json=[{"asset_id": asset.id, "variable": "主标题"}],
        bid_strategy_json={"type": "manual", "cap": 1.2},
        risk_controls_json=["每日复核 ROI", "异常点击及时停投"],
        next_steps_json=["运行 7 天实验", "复盘 CTR 与转化率"],
        confirm_status="confirmed",
        confirmed_by=actor.id,
        confirmed_at=now,
        confirm_remark="演示确认",
        model_name="mock",
        prompt_version="ad-v1",
        schema_version="ad-v1",
        provider_name="mock",
        input_snapshot_json={"asset_ids": [asset.id], "link_ids": [link.id]},
        raw_output="demo",
        generated_by=actor.id,
        version_no=1,
    )
    session.add(recommendation)
    session.flush()
    experiment = AdExperiment(
        product_id=product.id,
        recommendation_id=recommendation.id,
        related_asset_id=asset.id,
        related_link_id=link.id,
        experiment_name="演示｜通勤主图 7 天实验",
        target_text="提升有效点击与购买转化",
        audience_text="20～35 岁都市通勤人群",
        budget_amount=Decimal("1400.00"),
        success_metric_text="CTR ≥ 4%，ROI ≥ 3",
        hypothesis_text="轻量场景表达可降低携带顾虑",
        experiment_status="finished",
        version_no=1,
    )
    session.add(experiment)
    session.flush()
    session.add(
        AdExperiment(
            product_id=product.id,
            recommendation_id=recommendation.id,
            related_asset_id=asset.id,
            related_link_id=link.id,
            experiment_name="演示｜深色款待确认实验",
            target_text="验证颜色偏好",
            audience_text="商务通勤人群",
            budget_amount=Decimal("600.00"),
            success_metric_text="CTR ≥ 3.5%",
            hypothesis_text="深色款更适合商务场景",
            experiment_status="draft",
            version_no=1,
        )
    )
    ctr, conversion_rate, roi = calculate_metrics(
        impressions=20000,
        clicks=920,
        conversions=58,
        spend=Decimal("1400.00"),
        revenue=Decimal("7482.00"),
    )
    performance = PerformanceRecord(
        product_id=product.id,
        creative_plan_id=plan.id,
        generated_asset_id=asset.id,
        promotion_link_id=link.id,
        experiment_id=experiment.id,
        period_start=date(2026, 9, 1),
        period_end=date(2026, 9, 7),
        impressions=20000,
        clicks=920,
        ctr=ctr,
        conversions=58,
        conversion_rate=conversion_rate,
        spend=Decimal("1400.00"),
        revenue=Decimal("7482.00"),
        roi=roi,
        notes="演示实验经营数据",
        record_status="active",
        version_no=1,
        created_by=actor.id,
        updated_by=actor.id,
    )
    session.add(performance)
    session.flush()
    report = ReviewReport(
        product_id=product.id,
        period_start=performance.period_start,
        period_end=performance.period_end,
        summary_text="演示周期内点击与产出达到预期，轻量通勤方向值得继续验证。",
        insights_json=["CTR 4.6%，主图对目标人群有吸引力", "ROI 5.34，具备放量空间"],
        problem_analysis_json=["样本仅覆盖 7 天", "需要验证其他颜色 SKU"],
        next_actions_json=["复制实验到深色款", "增加杯盖易清洗证据", "逐步提升预算"],
        input_snapshot_json={"records": [{"id": performance.id}], "marker": DEMO_MARKER},
        model_name="mock",
        prompt_version="review-v1",
        provider_name="mock",
        schema_version="review-v1",
        raw_output="demo",
        generated_by=actor.id,
        version_no=1,
    )
    session.add(report)
    session.flush()
    session.add(
        ReviewReportRevision(
            review_report_id=report.id,
            version_no=1,
            summary_text=report.summary_text,
            insights_json=report.insights_json,
            problem_analysis_json=report.problem_analysis_json,
            next_actions_json=report.next_actions_json,
            changed_by=actor.id,
        )
    )
    next_diagnosis = ProductDiagnosis(
        product_id=product.id,
        source_type="review",
        source_review_report_id=report.id,
        positioning="延续轻量通勤定位，并扩展多色选择",
        price_band="维持中价格带",
        audience_insights="已验证通勤人群对轻量卖点响应积极",
        pain_points="补充杯盖清洁与多色选择",
        selling_point_analysis="保留轻量核心，增加结构细节证据",
        risks="放量后流量质量可能下降",
        recommendations="分阶段提预算并测试深色款",
        raw_output="demo",
        input_snapshot_json={"source_review": {"id": report.id}},
        model_name="mock",
        provider_name="mock",
        prompt_version="diagnosis-v1",
        schema_version="diagnosis-v1",
        generated_by=actor.id,
        version_no=1,
    )
    session.add(next_diagnosis)
    add_audit_log(
        session,
        actor_user_id=actor.id,
        action="demo_data.initialize",
        target_type="store",
        target_id=store.id,
        request_id=request_id,
        detail={"marker": DEMO_MARKER, "product_id": product.id},
    )
    session.commit()
    return _response(session, store, created=True)
