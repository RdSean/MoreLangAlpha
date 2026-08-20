"""The current migration chain must be usable without financial tables."""

from __future__ import annotations

from pathlib import Path
import runpy


FINANCE_MIGRATION_FILES = (
    "002_add_price_trigger_type.py",
    "005_add_insight_generating_unique_index.py",
    "007_market_insights_user_id_to_varchar.py",
    "014_add_chart_annotations.py",
)

RETIRED_SCHEMA_TERMS = (
    "market_insights",
    "chart_annotations",
    "symbol",
    "ticker",
    "price",
)


def test_follow_up_migrations_do_not_reference_retired_finance_schema():
    migration_dir = Path(__file__).parents[3] / "migrations/versions"

    for filename in FINANCE_MIGRATION_FILES:
        migration_source = (migration_dir / filename).read_text()
        assert not [term for term in RETIRED_SCHEMA_TERMS if term in migration_source]


def test_automation_code_has_no_price_trigger_or_monitor_service():
    root = Path(__file__).parents[3]
    for relative_path in (
        "src/server/database/automation.py",
        "src/server/handlers/automation_handler.py",
        "src/server/services/automation_executor.py",
        "src/server/models/automation.py",
        "src/tools/automation/tools.py",
    ):
        source = (root / relative_path).read_text()
        assert "trigger_type = 'price'" not in source
        assert 'trigger_type") == "price"' not in source
        assert 'Literal["cron", "once", "price"]' not in source

    assert not (root / "src/server/services/price_monitor.py").exists()


def test_household_llm_pool_migration_follows_teaching_archive_staging():
    """The household model pool is the next linear migration after 032."""
    migration_dir = Path(__file__).parents[3] / "migrations/versions"
    migration = runpy.run_path(str(migration_dir / "033_add_household_llm_pool.py"))

    assert migration["revision"] == "033"
    assert migration["down_revision"] == "032"
