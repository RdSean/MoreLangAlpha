from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest


@pytest.mark.asyncio
async def test_deletion_rejects_student_before_database_mutation(monkeypatch):
    from src.server.services import education_textbooks as service

    monkeypatch.setattr(
        service, "get_household_context_for_parent", AsyncMock(return_value=None)
    )
    with pytest.raises(service.TextbookPermissionError):
        await service.delete_managed_textbook(
            parent_user_id="student", textbook_id=uuid4()
        )


@pytest.mark.asyncio
async def test_cleanup_deletes_only_exact_book_prefix(monkeypatch):
    from src.server.services import education_book_deletion as service

    household, book = uuid4(), uuid4()
    prefix = f"education/{household}/textbooks/{book}/"
    delete = Mock(return_value=True)
    monkeypatch.setattr(service, "is_storage_enabled", lambda: True)
    monkeypatch.setattr(
        service,
        "list_object_keys",
        Mock(return_value=[prefix + "source/a.md", prefix + "materials/b.md"]),
    )
    monkeypatch.setattr(service, "delete_object", delete)
    await service.delete_textbook_objects(household_id=household, textbook_id=book)
    assert [call.args[0] for call in delete.call_args_list] == [
        prefix + "source/a.md",
        prefix + "materials/b.md",
    ]


@pytest.mark.asyncio
async def test_cleanup_rejects_out_of_prefix_before_any_delete(monkeypatch):
    from src.server.services import education_book_deletion as service

    delete = Mock(return_value=True)
    monkeypatch.setattr(service, "is_storage_enabled", lambda: True)
    monkeypatch.setattr(
        service, "list_object_keys", Mock(return_value=["documents/original.pdf"])
    )
    monkeypatch.setattr(service, "delete_object", delete)
    with pytest.raises(RuntimeError):
        await service.delete_textbook_objects(household_id=uuid4(), textbook_id=uuid4())
    delete.assert_not_called()


@pytest.mark.asyncio
async def test_cleanup_storage_failure_is_not_success(monkeypatch):
    from src.server.services import education_book_deletion as service

    household, book = uuid4(), uuid4()
    prefix = f"education/{household}/textbooks/{book}/"
    monkeypatch.setattr(service, "is_storage_enabled", lambda: True)
    monkeypatch.setattr(
        service, "list_object_keys", Mock(return_value=[prefix + "a.md"])
    )
    monkeypatch.setattr(service, "delete_object", Mock(return_value=False))
    with pytest.raises(RuntimeError):
        await service.delete_textbook_objects(household_id=household, textbook_id=book)


@pytest.mark.asyncio
async def test_cleanup_failed_attempt_keeps_durable_record(monkeypatch):
    from src.server.services import education_book_deletion as service

    row = {"textbook_id": uuid4(), "household_id": uuid4(), "lease_token": uuid4()}
    finish = AsyncMock()
    monkeypatch.setattr(
        service, "claim_textbook_cleanup", AsyncMock(side_effect=[row, None])
    )
    monkeypatch.setattr(
        service,
        "delete_textbook_objects",
        AsyncMock(side_effect=RuntimeError("storage")),
    )
    monkeypatch.setattr(service, "finish_textbook_cleanup", finish)
    assert await service.cleanup_deleted_textbooks_once() == 0
    finish.assert_awaited_once_with(
        textbook_id=row["textbook_id"], lease_token=row["lease_token"], succeeded=False
    )


@pytest.mark.asyncio
async def test_cleanup_success_removes_durable_record(monkeypatch):
    from src.server.services import education_book_deletion as service

    row = {"textbook_id": uuid4(), "household_id": uuid4(), "lease_token": uuid4()}
    finish = AsyncMock()
    monkeypatch.setattr(
        service, "claim_textbook_cleanup", AsyncMock(side_effect=[row, None])
    )
    monkeypatch.setattr(service, "delete_textbook_objects", AsyncMock())
    monkeypatch.setattr(service, "finish_textbook_cleanup", finish)
    assert await service.cleanup_deleted_textbooks_once() == 1
    finish.assert_awaited_once_with(
        textbook_id=row["textbook_id"], lease_token=row["lease_token"], succeeded=True
    )
