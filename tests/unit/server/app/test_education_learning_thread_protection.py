"""Generic thread mutations must not break assignment-scoped learning evidence."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.server.utils.api import get_current_user_id
from tests.conftest import create_test_app


THREADS_MOD = "src.server.app.threads.crud"


@pytest.mark.asyncio
async def test_student_cannot_delete_a_canonical_learning_thread():
    from src.server.app.threads import router

    app = create_test_app(router)
    app.dependency_overrides[get_current_user_id] = lambda: "student-1"

    runner = MagicMock()

    @asynccontextmanager
    async def exclusive(*_args, **_kwargs):
        yield MagicMock(conn=MagicMock())

    runner.exclusive = exclusive
    with (
        patch(f"{THREADS_MOD}.auth_api.require_thread_owner", new=AsyncMock()),
        patch(
            f"{THREADS_MOD}.get_student_learning_space_for_thread",
            new=AsyncMock(return_value={"assignment_id": "assignment-1"}),
            create=True,
        ),
        patch(
            "src.server.services.thread_mutation.ThreadMutationRunner.get_instance",
            return_value=runner,
        ),
        patch(f"{THREADS_MOD}.delete_thread", new=AsyncMock()),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.delete("/api/v1/threads/thread-1")

    assert response.status_code == 409
    assert "learning" in response.json()["detail"].lower()
