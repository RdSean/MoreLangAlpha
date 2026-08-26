"""Private metadata persistence for household-scoped education assets."""

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

from psycopg.rows import dict_row

from src.server.database.pool import get_db_connection


async def insert_education_asset(
    *,
    asset_id: str,
    household_id: str,
    created_by_user_id: str,
    storage_key: str,
    original_filename: str,
    content_type: str,
    size_bytes: int,
    staging_key: str | None = None,
    staging_slot: int | None = None,
) -> dict[str, Any] | None:
    """Record an uploaded object only while its creator remains a household member."""
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                INSERT INTO education_assets (
                    asset_id, household_id, created_by_user_id, storage_key,
                    original_filename, content_type, size_bytes, staging_key, staging_slot, created_at
                )
                SELECT %s, memberships.household_id, %s, %s, %s, %s, %s, %s, %s, NOW()
                FROM education_memberships AS memberships
                WHERE memberships.household_id = %s AND memberships.user_id = %s
                RETURNING asset_id, household_id, created_by_user_id, storage_key,
                          original_filename, content_type, size_bytes, staging_key, staging_slot, created_at
                """,
                (
                    asset_id,
                    created_by_user_id,
                    storage_key,
                    original_filename,
                    content_type,
                    size_bytes,
                    staging_key,
                    staging_slot,
                    household_id,
                    created_by_user_id,
                ),
            )
            row = await cur.fetchone()
    return dict(row) if row else None


async def get_staged_education_asset(
    *, household_id: str, created_by_user_id: str, staging_key: str, staging_slot: int,
) -> dict[str, Any] | None:
    """Return an existing attachment reserved by the same logical request."""
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT asset_id, household_id, created_by_user_id, storage_key,
                       original_filename, content_type, size_bytes, staging_key,
                       staging_slot, created_at
                FROM education_assets
                WHERE household_id = %s AND created_by_user_id = %s
                  AND staging_key = %s AND staging_slot = %s
                """,
                (household_id, created_by_user_id, staging_key, staging_slot),
            )
            row = await cur.fetchone()
    return dict(row) if row else None


async def delete_unreferenced_education_asset(
    *, asset_id: str, created_by_user_id: str,
) -> dict[str, Any] | None:
    """Delete creator-owned metadata only when no education record references it."""
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    DELETE FROM education_assets AS assets
                    WHERE assets.asset_id = %s
                      AND assets.created_by_user_id = %s
                      AND NOT EXISTS (
                          SELECT 1 FROM education_task_material_assets AS materials
                          WHERE materials.asset_id = assets.asset_id
                      )
                      AND NOT EXISTS (
                          SELECT 1 FROM education_task_submission_assets AS submissions
                          WHERE submissions.asset_id = assets.asset_id
                      )
                      AND NOT EXISTS (
                          SELECT 1 FROM education_textbook_sources AS sources
                          WHERE sources.asset_id = assets.asset_id
                      )
                    RETURNING asset_id, household_id, created_by_user_id, storage_key,
                              original_filename, content_type, size_bytes, created_at
                    """,
                    (asset_id, created_by_user_id),
                )
                row = await cur.fetchone()
    return dict(row) if row else None


@asynccontextmanager
async def claim_unreferenced_education_asset(
    *, asset_id: str, created_by_user_id: str,
) -> AsyncIterator[
    tuple[
        dict[str, Any] | None,
        Callable[[], Awaitable[dict[str, Any] | None]] | None,
    ]
]:
    """Lock an unreferenced asset until the caller deletes its storage object."""
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    SELECT assets.asset_id, assets.household_id, assets.created_by_user_id,
                           assets.storage_key, assets.original_filename, assets.content_type,
                           assets.size_bytes, assets.created_at
                    FROM education_assets AS assets
                    WHERE assets.asset_id = %s
                      AND assets.created_by_user_id = %s
                      AND NOT EXISTS (
                          SELECT 1 FROM education_task_material_assets AS materials
                          WHERE materials.asset_id = assets.asset_id
                      )
                      AND NOT EXISTS (
                          SELECT 1 FROM education_task_submission_assets AS submissions
                          WHERE submissions.asset_id = assets.asset_id
                      )
                      AND NOT EXISTS (
                          SELECT 1 FROM education_textbook_sources AS sources
                          WHERE sources.asset_id = assets.asset_id
                      )
                    FOR UPDATE OF assets
                    """,
                    (asset_id, created_by_user_id),
                )
                row = await cur.fetchone()
                if not row:
                    yield None, None
                    return

                async def delete_claimed_metadata() -> dict[str, Any] | None:
                    await cur.execute(
                        """
                        DELETE FROM education_assets
                        WHERE asset_id = %s AND created_by_user_id = %s
                        RETURNING asset_id, household_id, created_by_user_id, storage_key,
                                  original_filename, content_type, size_bytes, created_at
                        """,
                        (asset_id, created_by_user_id),
                    )
                    deleted_row = await cur.fetchone()
                    return dict(deleted_row) if deleted_row else None

                yield dict(row), delete_claimed_metadata


async def get_education_asset_for_user(
    *, user_id: str, asset_id: str
) -> dict[str, Any] | None:
    """Return an asset only when the requester belongs to its household."""
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT assets.asset_id, assets.household_id, assets.created_by_user_id,
                       assets.storage_key, assets.original_filename,
                       assets.content_type, assets.size_bytes, assets.created_at
                FROM education_assets AS assets
                JOIN education_memberships AS memberships
                  ON memberships.household_id = assets.household_id
                WHERE assets.asset_id = %s AND memberships.user_id = %s
                """,
                (asset_id, user_id),
            )
            row = await cur.fetchone()
    return dict(row) if row else None


async def list_education_assets_for_parent(
    *, parent_user_id: str
) -> list[dict[str, Any]]:
    """List only candidate asset metadata owned by the parent's household."""
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT assets.asset_id, assets.household_id, assets.created_by_user_id,
                       assets.original_filename, assets.content_type, assets.size_bytes,
                       assets.created_at
                FROM education_assets AS assets
                JOIN education_memberships AS memberships
                  ON memberships.household_id = assets.household_id
                WHERE memberships.user_id = %s AND memberships.role = 'parent'
                ORDER BY assets.created_at DESC
                """,
                (parent_user_id,),
            )
            rows = await cur.fetchall()
    return [dict(row) for row in rows]
