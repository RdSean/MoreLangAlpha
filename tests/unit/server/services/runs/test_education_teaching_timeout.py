"""Dedicated duration contracts for managed textbook root runs."""

from types import SimpleNamespace

from src.config import settings
from src.server.services.runs.executor import LocalRunExecutor


def test_education_teaching_timeouts_are_deployment_configured(monkeypatch):
    infrastructure = SimpleNamespace(
        education_teaching_workflow_timeout=86_400,
        education_teaching_abandoned_timeout=86_400,
    )
    monkeypatch.setattr(settings, "get_infrastructure_config", lambda: infrastructure)

    assert settings.get_education_teaching_workflow_timeout() == 86_400
    assert settings.get_education_teaching_abandoned_timeout() == 86_400


def test_local_executor_uses_the_managed_teaching_disconnect_window():
    executor = object.__new__(LocalRunExecutor)
    executor.abandoned_timeout = 21_600

    assert executor._abandoned_timeout_for_metadata(
        {"managed_execution": {"kind": "education_teaching"}}
    ) == 86_400
    assert executor._abandoned_timeout_for_metadata(
        {"managed_execution": {"kind": "education_book_pipeline"}}
    ) == 86_400
    assert executor._abandoned_timeout_for_metadata(
        {"managed_execution": {"kind": "education_lesson"}}
    ) == 86_400
    assert executor._abandoned_timeout_for_metadata({}) == 21_600
