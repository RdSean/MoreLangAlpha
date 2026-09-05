"""Safe terminal metadata assembly for household model billing."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_finalize_allow_lists_household_model_runtime_metadata():
    """The executor may carry runtime config, but terminal metadata may not."""
    from src.server.services.runs.finalization import assemble_finalize_artifacts

    _, _, _, _, metadata = await assemble_finalize_artifacts(
        ("thread-1", "run-1"),
        metadata={
            "msg_type": "flash",
            "is_byok": True,
            "llm_runtime": {
                "credential_source": "household",
                "household_id": "11111111-1111-1111-1111-111111111111",
                "family_endpoint_id": "22222222-2222-2222-2222-222222222222",
                "display_name": "Family DeepSeek Flash",
                "provider": "deepseek",
                "model_id": "deepseek-chat",
                "api_key": "family-secret-key",
                "base_url": "https://family.example/v1",
            },
        },
        status="completed",
        phase="completed",
        handler=None,
        cancelled_by_user=False,
        workspace_id="workspace-1",
        user_id="student-1",
    )

    assert metadata["llm_runtime"] == {
        "credential_source": "household",
        "household_id": "11111111-1111-1111-1111-111111111111",
        "display_name": "Family DeepSeek Flash",
        "provider": "deepseek",
        "model_id": "deepseek-chat",
    }
    assert "family-secret-key" not in str(metadata)
    assert "family.example" not in str(metadata)


@pytest.mark.asyncio
async def test_usage_writer_passes_household_runtime_snapshot_to_persistence():
    """The finalized run carries its safe provenance into the usage writer."""
    from src.server.services.runs.coordinator import (
        RunCoordinator,
        RunHandle,
        RunOutcome,
    )

    runtime = {
        "credential_source": "household",
        "household_id": "11111111-1111-1111-1111-111111111111",
        "family_endpoint_id": "22222222-2222-2222-2222-222222222222",
        "display_name": "Family DeepSeek Flash",
        "provider": "deepseek",
        "model_id": "deepseek-chat",
    }
    usage = MagicMock()
    usage.track_llm_usage = AsyncMock()
    usage.persist_usage = AsyncMock(return_value=True)
    handle = RunHandle(
        run_id="run-1",
        thread_id="thread-1",
        turn_index=0,
        attempt_no=1,
        msg_type="flash",
        workspace_id="workspace-1",
        user_id="student-1",
        is_byok=True,
    )
    outcome = RunOutcome(
        status="completed",
        metadata={"msg_type": "flash", "is_byok": True, "llm_runtime": runtime},
        per_call_records=[{"model": "deepseek-chat"}],
    )

    with patch(
        "src.server.services.persistence.usage.UsagePersistenceService",
        return_value=usage,
    ):
        writer = RunCoordinator()._build_usage_writer(handle, outcome)
        await writer(MagicMock(), "completed")

    usage.persist_usage.assert_awaited_once_with(
        response_id="run-1",
        msg_type="flash",
        deepthinking=False,
        status="completed",
        conn=usage.persist_usage.await_args.kwargs["conn"],
        is_byok=True,
        llm_runtime_metadata=runtime,
    )
