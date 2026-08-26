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


def test_household_shared_models_migration_follows_teaching_archive_staging():
    """The household shared-model schema is the next linear migration after 032."""
    migration_dir = Path(__file__).parents[3] / "migrations/versions"
    migration = runpy.run_path(str(migration_dir / "033_add_household_llm_pool.py"))

    assert migration["revision"] == "033"
    assert migration["down_revision"] == "032"


def test_homework_workflow_migration_follows_seeded_dictionaries():
    """The workflow upgrade depends on the homework dictionary foreign keys."""
    migration_dir = Path(__file__).parents[3] / "migrations/versions"
    migration = runpy.run_path(
        str(migration_dir / "035_add_education_homework_workflow.py")
    )

    assert migration["revision"] == "035"
    assert migration["down_revision"] == "034"


def test_homework_workflow_repair_follows_initial_workflow_schema():
    migration_dir = Path(__file__).parents[3] / "migrations/versions"
    migration = runpy.run_path(
        str(migration_dir / "036_repair_education_homework_workflow.py")
    )

    assert migration["revision"] == "036"
    assert migration["down_revision"] == "035"


def test_weekday_validation_repair_follows_workflow_compatibility_repair():
    migration_dir = Path(__file__).parents[3] / "migrations/versions"
    migration = runpy.run_path(
        str(migration_dir / "037_repair_education_weekday_validation.py")
    )

    assert migration["revision"] == "037"
    assert migration["down_revision"] == "036"


def test_recurrence_revalidation_follows_weekday_validation_repair():
    migration_dir = Path(__file__).parents[3] / "migrations/versions"
    migration = runpy.run_path(
        str(migration_dir / "038_revalidate_education_homework_recurrence.py")
    )

    assert migration["revision"] == "038"
    assert migration["down_revision"] == "037"


def test_homework_state_cutover_follows_compatibility_migrations():
    migration_dir = Path(__file__).parents[3] / "migrations/versions"
    migration = runpy.run_path(
        str(migration_dir / "039_finalize_education_homework_workflow.py")
    )

    assert migration["revision"] == "039"
    assert migration["down_revision"] == "038"
