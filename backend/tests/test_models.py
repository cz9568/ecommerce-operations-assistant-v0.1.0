from backend.app import models  # noqa: F401
from backend.app.database import Base


def test_core_tables_are_registered() -> None:
    expected_tables = {
        "users",
        "stores",
        "products",
        "product_skus",
        "inventory_items",
        "inventory_movements",
        "inventory_advice_runs",
        "inventory_advice_items",
        "competitors",
        "product_diagnoses",
        "ai_usage_logs",
        "creative_plans",
        "creative_plan_revisions",
        "generation_jobs",
        "generation_job_events",
        "generated_assets",
        "promotion_links",
        "ad_recommendations",
        "ad_experiments",
        "performance_records",
        "review_reports",
        "review_report_revisions",
        "import_batches",
        "audit_logs",
    }

    assert expected_tables <= set(Base.metadata.tables)
    assert len(Base.metadata.tables) == 33


def test_all_tables_have_primary_keys() -> None:
    without_primary_key = [
        table.name for table in Base.metadata.sorted_tables if not table.primary_key.columns
    ]

    assert without_primary_key == []
