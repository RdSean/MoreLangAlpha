"""Safe read model for textbook usages of an owned library Document."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from src.server.database import education_textbooks as education_textbook_repository


_SAFE_USAGE_FIELDS = (
    "document_id",
    "producer_job_id",
    "primary_artifact_id",
    "textbook_id",
    "textbook_title",
    "content_version_id",
    "content_version_sequence",
    "artifact_position",
    "teaching_package_id",
    "teaching_package_sequence",
    "status",
    "has_asset_manifest",
    "created_at",
)


def _safe_usage(row: Mapping[str, Any]) -> dict[str, Any]:
    return {field: row.get(field) for field in _SAFE_USAGE_FIELDS}


async def list_document_teaching_usages(
    *, owner_user_id: str, document_id: str
) -> list[dict[str, Any]]:
    """Return only public usage fields for the owner-scoped Document."""
    rows = await education_textbook_repository.list_document_teaching_usages(
        owner_user_id=owner_user_id,
        document_id=document_id,
    )
    return [_safe_usage(row) for row in rows]


async def can_read_document_teaching_usage(
    *, owner_user_id: str, document_id: str
) -> bool:
    """Return whether the owner may read usages under current memberships."""
    return (
        await education_textbook_repository.get_document_teaching_usage_access(
            owner_user_id=owner_user_id,
            document_id=document_id,
        )
        is True
    )
