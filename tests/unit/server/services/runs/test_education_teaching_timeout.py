"""Dedicated duration contracts for managed textbook root runs."""

from types import SimpleNamespace

from src.config import settings
from src.server.services.runs.executor import LocalRunExecutor


def test_education_book_timeouts_are_deployment_configured(monkeypatch):
    infrastructure = SimpleNamespace(
        education_book_workflow_timeout=86_400,
        education_book_abandoned_timeout=86_400,
    )
    monkeypatch.setattr(settings, "get_infrastructure_config", lambda: infrastructure)

    assert settings.get_education_book_workflow_timeout() == 86_400
    assert settings.get_education_book_abandoned_timeout() == 86_400


def test_local_executor_only_recognizes_the_unified_education_book_kind(monkeypatch):
    executor = object.__new__(LocalRunExecutor)
    executor.abandoned_timeout = 21_600
    monkeypatch.setattr(
        "src.server.services.runs.executor.get_education_book_abandoned_timeout",
        lambda: 86_400,
    )

    assert (
        executor._abandoned_timeout_for_metadata(
            {"managed_execution": {"kind": "education_book"}}
        )
        == 86_400
    )
    for old_kind in (
        "education_teaching",
        "education_structure",
        "education_lesson",
        "education_book_pipeline",
    ):
        assert (
            executor._abandoned_timeout_for_metadata(
                {"managed_execution": {"kind": old_kind}}
            )
            == 21_600
        )
    assert executor._abandoned_timeout_for_metadata({}) == 21_600
