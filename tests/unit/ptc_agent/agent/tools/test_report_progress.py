"""Contracts for the managed progress stream tool."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_report_progress_emits_only_the_bounded_stage(monkeypatch):
    from ptc_agent.agent.tools.report_progress import create_report_progress_tool

    emitted: list[dict[str, object]] = []
    monkeypatch.setattr("langgraph.config.get_stream_writer", lambda: emitted.append)

    result = await create_report_progress_tool().ainvoke(
        {"stage": "structure_organizing"}
    )

    assert result == "Progress reported."
    assert emitted == [
        {
            "artifact_type": "report_progress",
            "artifact_id": "structure_organizing",
            "status": "running",
            "payload": {"stage": "structure_organizing"},
        }
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "stage",
    (
        "",
        " structure_reading",
        "structure-reading",
        "outputs/book.json",
        "UPPERCASE",
        "1_structure",
        "a" * 65,
    ),
)
async def test_report_progress_rejects_invalid_stage_without_emitting(
    monkeypatch, stage
):
    from ptc_agent.agent.tools.report_progress import create_report_progress_tool

    emitted: list[dict[str, object]] = []
    monkeypatch.setattr("langgraph.config.get_stream_writer", lambda: emitted.append)

    result = await create_report_progress_tool().ainvoke({"stage": stage})

    assert result == "Invalid progress stage; continue the task."
    assert emitted == []


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_at", ("get_writer", "write"))
async def test_report_progress_writer_failure_does_not_fail_the_agent(
    monkeypatch, failure_at
):
    from ptc_agent.agent.tools.report_progress import create_report_progress_tool

    def fail():
        raise RuntimeError("stream unavailable")

    if failure_at == "get_writer":
        monkeypatch.setattr("langgraph.config.get_stream_writer", fail)
    else:
        monkeypatch.setattr("langgraph.config.get_stream_writer", lambda: fail)

    result = await create_report_progress_tool().ainvoke(
        {"stage": "material_writing"}
    )

    assert result == "Progress reporting unavailable; continue the task."
