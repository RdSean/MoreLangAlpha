from __future__ import annotations

from contextlib import asynccontextmanager

import pytest

from src.server.database import documents


def _patch_connection(monkeypatch, mock_connection):
    @asynccontextmanager
    async def fake_connection():
        yield mock_connection

    monkeypatch.setattr(documents, "get_db_connection", fake_connection)


@pytest.mark.asyncio
async def test_document_lookup_always_scopes_owner(
    mock_connection,
    mock_cursor,
    monkeypatch,
) -> None:
    _patch_connection(monkeypatch, mock_connection)
    mock_cursor.fetchone.return_value = {"document_id": "doc-A1b2C3d4E5f6"}

    result = await documents.get_document(
        owner_user_id="owner-1",
        document_id="doc-A1b2C3d4E5f6",
    )

    assert result == {"document_id": "doc-A1b2C3d4E5f6"}
    sql, params = mock_cursor.execute.await_args.args
    assert "documents.owner_user_id = %s" in sql
    assert params == ("doc-A1b2C3d4E5f6", "owner-1")


@pytest.mark.asyncio
async def test_document_create_rejects_cross_owner_dataset_membership(
    mock_connection,
    mock_cursor,
    monkeypatch,
) -> None:
    _patch_connection(monkeypatch, mock_connection)
    mock_cursor.fetchone.return_value = {"document_id": "doc-A1b2C3d4E5f6"}
    mock_cursor.rowcount = 0

    with pytest.raises(ValueError, match="Dataset"):
        await documents.create_document(
            owner_user_id="owner-1",
            document_id="doc-A1b2C3d4E5f6",
            original_filename="source.pdf",
            media_type="application/pdf",
            document_format="pdf",
            source_storage_key="documents/doc-A1b2C3d4E5f6/source",
            source_size_bytes=128,
            source_sha256="a" * 64,
            dataset_ids=("dts-G7h8I9j0K1l2",),
        )

    membership_call = mock_cursor.execute.await_args_list[1]
    sql, params = membership_call.args
    assert "document_datasets.owner_user_id = %s" in sql
    assert params[-2:] == ("owner-1", ["dts-G7h8I9j0K1l2"])


@pytest.mark.asyncio
async def test_list_documents_combines_all_server_filters(
    mock_connection,
    mock_cursor,
    monkeypatch,
) -> None:
    _patch_connection(monkeypatch, mock_connection)
    mock_cursor.fetchone.return_value = {"total": 0}
    filters = documents.DocumentListFilter(
        query="algebra",
        dataset_id="dts-A1b2C3d4E5f6",
        tag_ids=("tag-A1b2C3d4E5f6", "tag-G7h8I9j0K1l2"),
        media_type="application/pdf",
        classification="text_based",
        parse_status="completed",
        limit=25,
        offset=50,
    )

    rows, total = await documents.list_documents(
        owner_user_id="owner-1",
        filters=filters,
    )

    assert rows == []
    assert total == 0
    count_sql, count_params = mock_cursor.execute.await_args_list[0].args
    page_sql, page_params = mock_cursor.execute.await_args_list[1].args
    for fragment in (
        "documents.owner_user_id = %s",
        "documents.original_filename ILIKE %s",
        "document_dataset_items",
        "document_tag_assignments",
        "documents.media_type = %s",
        "document_inspections",
        "document_parse_jobs",
    ):
        assert fragment in count_sql
        assert fragment in page_sql
    assert count_params[0] == "owner-1"
    assert page_params[-2:] == (25, 50)


@pytest.mark.asyncio
async def test_list_documents_gets_total_before_limit_and_offset(
    mock_connection,
    mock_cursor,
    monkeypatch,
) -> None:
    _patch_connection(monkeypatch, mock_connection)
    mock_cursor.fetchone.return_value = {"total": 42}
    mock_cursor.fetchall.return_value = [{"document_id": "doc-A1b2C3d4E5f6"}]

    rows, total = await documents.list_documents(
        owner_user_id="owner-1",
        filters=documents.DocumentListFilter(limit=10, offset=20),
    )

    count_sql, count_params = mock_cursor.execute.await_args_list[0].args
    page_sql, page_params = mock_cursor.execute.await_args_list[1].args
    assert "LIMIT" not in count_sql
    assert "OFFSET" not in count_sql
    assert count_params == ("owner-1",)
    assert "LIMIT %s OFFSET %s" in page_sql
    assert page_params == ("owner-1", 10, 20)
    assert rows == [{"document_id": "doc-A1b2C3d4E5f6"}]
    assert total == 42


@pytest.mark.asyncio
async def test_same_document_can_have_multiple_datasets_and_tags(
    mock_connection,
    mock_cursor,
    monkeypatch,
) -> None:
    _patch_connection(monkeypatch, mock_connection)
    mock_cursor.fetchone.return_value = {"document_id": "doc-A1b2C3d4E5f6"}
    mock_cursor.rowcount = 2

    await documents.replace_dataset_memberships(
        owner_user_id="owner-1",
        document_id="doc-A1b2C3d4E5f6",
        dataset_ids=("dts-A1b2C3d4E5f6", "dts-G7h8I9j0K1l2"),
    )
    await documents.replace_tag_assignments(
        owner_user_id="owner-1",
        document_id="doc-A1b2C3d4E5f6",
        tag_ids=("tag-A1b2C3d4E5f6", "tag-G7h8I9j0K1l2"),
    )

    dataset_insert = mock_cursor.execute.await_args_list[2]
    tag_insert = mock_cursor.execute.await_args_list[5]
    assert "ANY(%s)" in dataset_insert.args[0]
    assert dataset_insert.args[1][-1] == [
        "dts-A1b2C3d4E5f6",
        "dts-G7h8I9j0K1l2",
    ]
    assert "ANY(%s)" in tag_insert.args[0]
    assert tag_insert.args[1][-1] == [
        "tag-A1b2C3d4E5f6",
        "tag-G7h8I9j0K1l2",
    ]


@pytest.mark.parametrize(
    ("replace", "ids_name"),
    [
        (documents.replace_dataset_memberships, "dataset_ids"),
        (documents.replace_tag_assignments, "tag_ids"),
    ],
)
@pytest.mark.asyncio
async def test_empty_membership_replacement_still_rejects_unowned_document(
    replace,
    ids_name,
    mock_connection,
    mock_cursor,
    monkeypatch,
) -> None:
    _patch_connection(monkeypatch, mock_connection)
    mock_cursor.fetchone.return_value = None

    with pytest.raises(ValueError, match="Document"):
        await replace(
            owner_user_id="owner-1",
            document_id="doc-A1b2C3d4E5f6",
            **{ids_name: ()},
        )

    sql, params = mock_cursor.execute.await_args.args
    assert "FOR UPDATE" in sql
    assert "owner_user_id = %s" in sql
    assert params == ("doc-A1b2C3d4E5f6", "owner-1")


@pytest.mark.asyncio
async def test_tag_normalized_name_is_bound_with_owner(
    mock_connection,
    mock_cursor,
    monkeypatch,
) -> None:
    _patch_connection(monkeypatch, mock_connection)
    mock_cursor.fetchone.return_value = {
        "tag_id": "tag-A1b2C3d4E5f6",
        "normalized_name": "mathematics",
    }

    result = await documents.create_tag(
        owner_user_id="owner-1",
        tag_id="tag-A1b2C3d4E5f6",
        name="Mathematics",
        normalized_name="mathematics",
    )

    sql, params = mock_cursor.execute.await_args.args
    assert "owner_user_id" in sql
    assert "normalized_name" in sql
    assert "ON CONFLICT" not in sql
    assert params == (
        "tag-A1b2C3d4E5f6",
        "owner-1",
        "Mathematics",
        "mathematics",
    )
    assert result["normalized_name"] == "mathematics"


@pytest.mark.asyncio
async def test_dataset_crud_always_binds_owner(
    mock_connection,
    mock_cursor,
    monkeypatch,
) -> None:
    _patch_connection(monkeypatch, mock_connection)
    mock_cursor.fetchone.return_value = {"dataset_id": "dts-A1b2C3d4E5f6"}

    await documents.create_dataset(
        owner_user_id="owner-1",
        dataset_id="dts-A1b2C3d4E5f6",
        name="Mathematics",
        description="Algebra references",
    )
    await documents.get_dataset(
        owner_user_id="owner-1",
        dataset_id="dts-A1b2C3d4E5f6",
    )
    await documents.update_dataset(
        owner_user_id="owner-1",
        dataset_id="dts-A1b2C3d4E5f6",
        name="Advanced mathematics",
        description=None,
    )
    await documents.delete_dataset(
        owner_user_id="owner-1",
        dataset_id="dts-A1b2C3d4E5f6",
    )

    for call in mock_cursor.execute.await_args_list:
        sql, params = call.args
        assert "owner_user_id" in sql
        assert "owner-1" in params


@pytest.mark.asyncio
async def test_dataset_list_returns_document_counts_and_total(
    mock_connection,
    mock_cursor,
    monkeypatch,
) -> None:
    _patch_connection(monkeypatch, mock_connection)
    mock_cursor.fetchone.return_value = {"total": 3}
    mock_cursor.fetchall.return_value = [
        {"dataset_id": "dts-A1b2C3d4E5f6", "document_count": 2},
    ]

    rows, total = await documents.list_datasets(
        owner_user_id="owner-1",
        query="math",
        limit=10,
        offset=20,
    )

    count_sql, count_params = mock_cursor.execute.await_args_list[0].args
    page_sql, page_params = mock_cursor.execute.await_args_list[1].args
    assert "document_datasets.owner_user_id = %s" in count_sql
    assert "COUNT(*)" in count_sql
    assert count_params == ("owner-1", "%math%")
    assert "document_dataset_items" in page_sql
    assert "document_count" in page_sql
    assert page_params[-2:] == (10, 20)
    assert rows[0]["document_count"] == 2
    assert total == 3


@pytest.mark.asyncio
async def test_count_datasets_scopes_owner_and_search(
    mock_connection,
    mock_cursor,
    monkeypatch,
) -> None:
    _patch_connection(monkeypatch, mock_connection)
    mock_cursor.fetchone.return_value = {"total": 3}

    total = await documents.count_datasets(
        owner_user_id="owner-1",
        query="math",
    )

    sql, params = mock_cursor.execute.await_args.args
    assert "document_datasets.owner_user_id = %s" in sql
    assert params == ("owner-1", "%math%")
    assert total == 3


@pytest.mark.asyncio
async def test_tag_crud_and_list_always_bind_owner(
    mock_connection,
    mock_cursor,
    monkeypatch,
) -> None:
    _patch_connection(monkeypatch, mock_connection)
    mock_cursor.fetchone.return_value = {"tag_id": "tag-A1b2C3d4E5f6"}
    mock_cursor.fetchall.return_value = [{"tag_id": "tag-A1b2C3d4E5f6"}]

    await documents.get_tag(
        owner_user_id="owner-1",
        tag_id="tag-A1b2C3d4E5f6",
    )
    await documents.update_tag(
        owner_user_id="owner-1",
        tag_id="tag-A1b2C3d4E5f6",
        name="Math",
        normalized_name="math",
    )
    await documents.list_tags(owner_user_id="owner-1")
    await documents.delete_tag(
        owner_user_id="owner-1",
        tag_id="tag-A1b2C3d4E5f6",
    )

    for call in mock_cursor.execute.await_args_list:
        sql, params = call.args
        assert "owner_user_id" in sql
        assert "owner-1" in params


@pytest.mark.asyncio
async def test_document_update_and_delete_return_only_owned_row(
    mock_connection,
    mock_cursor,
    monkeypatch,
) -> None:
    _patch_connection(monkeypatch, mock_connection)
    mock_cursor.fetchone.return_value = {"document_id": "doc-A1b2C3d4E5f6"}

    await documents.update_document(
        owner_user_id="owner-1",
        document_id="doc-A1b2C3d4E5f6",
        original_filename="renamed.pdf",
    )
    await documents.delete_document(
        owner_user_id="owner-1",
        document_id="doc-A1b2C3d4E5f6",
    )

    for call in mock_cursor.execute.await_args_list:
        sql, params = call.args
        assert "owner_user_id = %s" in sql
        assert params[-1] == "owner-1"


@pytest.mark.asyncio
async def test_inspection_create_get_and_list_authorize_through_document(
    mock_connection,
    mock_cursor,
    monkeypatch,
) -> None:
    _patch_connection(monkeypatch, mock_connection)
    mock_cursor.fetchone.return_value = {"inspection_id": "ins-A1b2C3d4E5f6"}
    mock_cursor.fetchall.return_value = [
        {"inspection_id": "ins-A1b2C3d4E5f6"},
    ]

    await documents.create_inspection(
        owner_user_id="owner-1",
        inspection_id="ins-A1b2C3d4E5f6",
        document_id="doc-A1b2C3d4E5f6",
        inspector_id="pdf-inspector",
        inspector_name="PDF Inspector",
        inspector_version="1.17.0",
        status="completed",
        detected_format="pdf",
        classification="text_based",
        summary={"page_count": 3},
        details={},
    )
    await documents.get_inspection(
        owner_user_id="owner-1",
        inspection_id="ins-A1b2C3d4E5f6",
    )
    await documents.list_inspections(
        owner_user_id="owner-1",
        document_id="doc-A1b2C3d4E5f6",
    )

    create_sql, create_params = mock_cursor.execute.await_args_list[0].args
    assert "FROM documents" in create_sql
    assert "documents.owner_user_id = %s" in create_sql
    assert "owner-1" in create_params
    for call in mock_cursor.execute.await_args_list[1:]:
        sql, params = call.args
        assert "JOIN documents" in sql
        assert "documents.owner_user_id = %s" in sql
        assert "owner-1" in params


@pytest.mark.asyncio
async def test_finish_inspection_updates_only_owned_pending_row(
    mock_connection,
    mock_cursor,
    monkeypatch,
) -> None:
    _patch_connection(monkeypatch, mock_connection)
    mock_cursor.fetchone.return_value = {"inspection_id": "ins-A1b2C3d4E5f6"}

    await documents.finish_inspection(
        owner_user_id="owner-1",
        document_id="doc-A1b2C3d4E5f6",
        inspection_id="ins-A1b2C3d4E5f6",
        status="completed",
        detected_format="pdf",
        classification="text_based",
        summary={"page_count": 3},
        details={"pages_needing_ocr": []},
        error_code=None,
        error_message=None,
    )

    sql, params = mock_cursor.execute.await_args.args
    assert "FROM documents" in sql
    assert "document_inspections.status = 'pending'" in sql
    assert "documents.owner_user_id = %s" in sql
    assert params[-3:] == (
        "ins-A1b2C3d4E5f6",
        "doc-A1b2C3d4E5f6",
        "owner-1",
    )


@pytest.mark.asyncio
async def test_latest_successful_inspection_is_owner_scoped(
    mock_connection,
    mock_cursor,
    monkeypatch,
) -> None:
    _patch_connection(monkeypatch, mock_connection)
    mock_cursor.fetchone.return_value = {"inspection_id": "ins-A1b2C3d4E5f6"}

    result = await documents.get_latest_successful_inspection(
        owner_user_id="owner-1",
        document_id="doc-A1b2C3d4E5f6",
    )

    assert result == {"inspection_id": "ins-A1b2C3d4E5f6"}
    sql, params = mock_cursor.execute.await_args.args
    assert "document_inspections.status = 'completed'" in sql
    assert "documents.owner_user_id = %s" in sql
    assert "LIMIT 1" in sql
    assert params == ("doc-A1b2C3d4E5f6", "owner-1")


@pytest.mark.asyncio
async def test_artifact_get_and_list_authorize_through_document(
    mock_connection,
    mock_cursor,
    monkeypatch,
) -> None:
    _patch_connection(monkeypatch, mock_connection)
    mock_cursor.fetchone.return_value = {"artifact_id": "art-A1b2C3d4E5f6"}
    mock_cursor.fetchall.return_value = [
        {"artifact_id": "art-A1b2C3d4E5f6"},
    ]

    await documents.get_artifact(
        owner_user_id="owner-1",
        artifact_id="art-A1b2C3d4E5f6",
    )
    await documents.list_artifacts(
        owner_user_id="owner-1",
        document_id="doc-A1b2C3d4E5f6",
        producer_job_id="job-A1b2C3d4E5f6",
    )

    for call in mock_cursor.execute.await_args_list:
        sql, params = call.args
        assert "JOIN documents" in sql
        assert "documents.owner_user_id = %s" in sql
        assert "owner-1" in params


@pytest.mark.asyncio
async def test_parse_job_history_authorizes_through_document(
    mock_connection,
    mock_cursor,
    monkeypatch,
) -> None:
    _patch_connection(monkeypatch, mock_connection)
    mock_cursor.fetchall.return_value = [{"job_id": "job-A1b2C3d4E5f6"}]

    rows = await documents.list_parse_jobs(
        owner_user_id="owner-1",
        document_id="doc-A1b2C3d4E5f6",
        limit=10,
        offset=20,
    )

    sql, params = mock_cursor.execute.await_args.args
    assert "JOIN documents" in sql
    assert "documents.owner_user_id = %s" in sql
    assert params == ("doc-A1b2C3d4E5f6", "owner-1", 10, 20)
    assert rows == [{"job_id": "job-A1b2C3d4E5f6"}]
