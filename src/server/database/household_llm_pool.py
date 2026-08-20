"""Persistence primitives for the household-owned LLM model pool.

The database module deliberately has two read paths: public summaries never
decrypt credentials, while ``get_endpoint_for_runtime`` is the only function
that asks PostgreSQL to decrypt an API key.
"""

from __future__ import annotations

from typing import Any

from psycopg.rows import dict_row

from src.server.database.encryption import get_encryption_key as _get_encryption_key
from src.server.database.pool import get_db_connection


# An omitted API-key field is different from an explicit ``None`` (clear it).
API_KEY_UNSET = object()
FIELD_UNSET = object()


def _endpoint_summary(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    result = dict(row)
    result.pop("api_key", None)
    if "endpoint_id" in result and result["endpoint_id"] is not None:
        result["endpoint_id"] = str(result["endpoint_id"])
    if "household_id" in result and result["household_id"] is not None:
        result["household_id"] = str(result["household_id"])
    if "has_api_key" in result:
        result["masked_api_key"] = "********" if result.pop("has_api_key") else None
    result.setdefault("masked_api_key", None)
    # ``masked_key`` matches the existing user-BYOK response vocabulary;
    # retain the explicit API-key name for family API consumers as well.
    result.setdefault("masked_key", result["masked_api_key"])
    return result


def _student_endpoint_summary(row: dict[str, Any] | None) -> dict[str, Any] | None:
    """Project an endpoint for a student without URL or credential metadata."""
    result = _endpoint_summary(row)
    if result is None:
        return None
    for field in ("base_url", "masked_api_key", "masked_key", "created_by"):
        result.pop(field, None)
    return result


async def list_household_endpoints(
    household_id: str, *, include_disabled: bool = False
) -> list[dict[str, Any]]:
    """Return endpoint metadata without decrypting credentials."""
    where_enabled = "" if include_disabled else "AND enabled = TRUE"
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                f"""
                SELECT endpoint_id, household_id, display_name, provider, model_id,
                       base_url, enabled, sort_order, created_by, created_at, updated_at,
                       (api_key IS NOT NULL) AS has_api_key
                FROM household_llm_endpoints
                WHERE household_id = %s {where_enabled}
                ORDER BY sort_order, display_name, endpoint_id
                """,
                (household_id,),
            )
            rows = await cur.fetchall()
    return [_endpoint_summary(row) for row in rows]


async def get_endpoint_for_runtime(
    household_id: str, endpoint_id: str
) -> dict[str, Any] | None:
    """Fetch one enabled endpoint and decrypt its key for server-side use."""
    enc_key = _get_encryption_key()
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT endpoint_id, household_id, display_name, provider, model_id,
                       base_url, enabled, sort_order, created_by, created_at, updated_at,
                       CASE WHEN api_key IS NULL THEN NULL
                            ELSE pgp_sym_decrypt(api_key, %s) END AS api_key
                FROM household_llm_endpoints
                WHERE household_id = %s AND endpoint_id = %s AND enabled = TRUE
                """,
                (enc_key, household_id, endpoint_id),
            )
            row = await cur.fetchone()
    if not row:
        return None
    result = dict(row)
    result["endpoint_id"] = str(result["endpoint_id"])
    result["household_id"] = str(result["household_id"])
    return result


async def create_household_endpoint(
    household_id: str,
    created_by: str,
    *,
    display_name: str,
    provider: str,
    model_id: str,
    base_url: str | None = None,
    api_key: str | None = None,
    enabled: bool = True,
    sort_order: int = 0,
) -> dict[str, Any]:
    """Create an endpoint, encrypting the supplied key in PostgreSQL."""
    enc_key = _get_encryption_key()
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                INSERT INTO household_llm_endpoints
                    (household_id, display_name, provider, model_id, base_url,
                     api_key, enabled, sort_order, created_by)
                VALUES (%s, %s, %s, %s, %s,
                        CASE WHEN %s::text IS NULL THEN NULL
                             ELSE pgp_sym_encrypt(%s::text, %s::text) END,
                        %s, %s, %s)
                RETURNING endpoint_id, household_id, display_name, provider, model_id,
                          base_url, enabled, sort_order, created_by, created_at, updated_at,
                          (api_key IS NOT NULL) AS has_api_key
                """,
                (
                    household_id,
                    display_name,
                    provider,
                    model_id,
                    base_url,
                    api_key,
                    api_key,
                    enc_key,
                    enabled,
                    sort_order,
                    created_by,
                ),
            )
            row = await cur.fetchone()
    return _endpoint_summary(row) or {}


async def update_household_endpoint(
    household_id: str,
    endpoint_id: str,
    *,
    display_name: str | None | object = FIELD_UNSET,
    provider: str | None | object = FIELD_UNSET,
    model_id: str | None | object = FIELD_UNSET,
    base_url: str | None | object = FIELD_UNSET,
    api_key: str | None | object = API_KEY_UNSET,
    enabled: bool | None | object = FIELD_UNSET,
    sort_order: int | None | object = FIELD_UNSET,
) -> dict[str, Any] | None:
    """Update an endpoint while distinguishing omitted and cleared API keys."""
    assignments: list[str] = []
    values: list[Any] = []
    for column, value in (
        ("display_name", display_name),
        ("provider", provider),
        ("model_id", model_id),
        ("base_url", base_url),
        ("enabled", enabled),
        ("sort_order", sort_order),
    ):
        if value is not FIELD_UNSET:
            assignments.append(f"{column} = %s")
            values.append(value)
    enc_key: str | None = None
    if api_key is not API_KEY_UNSET:
        assignments.append(
            "api_key = CASE WHEN %s::text IS NULL THEN NULL ELSE pgp_sym_encrypt(%s::text, %s::text) END"
        )
        enc_key = _get_encryption_key()
        values.extend([api_key, api_key, enc_key])
    if not assignments:
        async with get_db_connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    SELECT endpoint_id, household_id, display_name, provider, model_id,
                           base_url, enabled, sort_order, created_by, created_at, updated_at,
                           (api_key IS NOT NULL) AS has_api_key
                    FROM household_llm_endpoints
                    WHERE household_id = %s AND endpoint_id = %s
                    """,
                    (household_id, endpoint_id),
                )
                row = await cur.fetchone()
        return _endpoint_summary(row)

    assignments.append("updated_at = NOW()")
    values.extend([household_id, endpoint_id])
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    f"""
                    UPDATE household_llm_endpoints
                    SET {", ".join(assignments)}
                    WHERE household_id = %s AND endpoint_id = %s
                    RETURNING endpoint_id, household_id, display_name, provider, model_id,
                              base_url, enabled, sort_order, created_by, created_at, updated_at,
                              (api_key IS NOT NULL) AS has_api_key
                    """,
                    values,
                )
                row = await cur.fetchone()
                if row and enabled is False:
                    # A disabled endpoint cannot remain the household default.
                    await cur.execute(
                        """
                        UPDATE household_llm_settings
                        SET default_endpoint_id = NULL, updated_at = NOW()
                        WHERE household_id = %s AND default_endpoint_id = %s
                        """,
                        (household_id, endpoint_id),
                    )
    return _endpoint_summary(row)


async def delete_household_endpoint(household_id: str, endpoint_id: str) -> bool:
    """Delete an endpoint and clean any household default in the same transaction."""
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor() as cur:
                await cur.execute(
                    "DELETE FROM household_llm_endpoints WHERE household_id = %s AND endpoint_id = %s",
                    (household_id, endpoint_id),
                )
                deleted = cur.rowcount > 0
                if deleted:
                    await cur.execute(
                        """
                        UPDATE household_llm_settings
                        SET default_endpoint_id = NULL, updated_at = NOW()
                        WHERE household_id = %s AND default_endpoint_id = %s
                        """,
                        (household_id, endpoint_id),
                    )
    return deleted


async def set_household_default(
    household_id: str, endpoint_id: str | None
) -> dict[str, Any]:
    """Set or clear a household default, refusing disabled/cross-household IDs."""
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor() as cur:
                if endpoint_id is not None:
                    await cur.execute(
                        """
                        SELECT 1 FROM household_llm_endpoints
                        WHERE household_id = %s AND endpoint_id = %s AND enabled = TRUE
                        """,
                        (household_id, endpoint_id),
                    )
                    if await cur.fetchone() is None:
                        return {
                            "household_id": household_id,
                            "default_endpoint_id": None,
                        }
                await cur.execute(
                    """
                    INSERT INTO household_llm_settings (household_id, default_endpoint_id)
                    VALUES (%s, %s)
                    ON CONFLICT (household_id) DO UPDATE
                    SET default_endpoint_id = EXCLUDED.default_endpoint_id, updated_at = NOW()
                    RETURNING household_id, default_endpoint_id, updated_at
                    """,
                    (household_id, endpoint_id),
                )
                row = await cur.fetchone()
    result = dict(row or {"household_id": household_id, "default_endpoint_id": None})
    result["household_id"] = str(result["household_id"])
    if result.get("default_endpoint_id") is not None:
        result["default_endpoint_id"] = str(result["default_endpoint_id"])
    return result


async def get_household_availability(
    household_id: str, user_id: str | None = None
) -> dict[str, Any]:
    """Return enabled summaries plus default/preference projections."""
    all_endpoints = await list_household_endpoints(household_id, include_disabled=True)
    endpoints = [row for row in all_endpoints if row["enabled"]]
    endpoint_by_id = {str(row["endpoint_id"]): row for row in endpoints}
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT s.default_endpoint_id
                FROM household_llm_settings AS s
                WHERE s.household_id = %s
                """,
                (household_id,),
            )
            settings = await cur.fetchone()
            preference = None
            if user_id is not None:
                await cur.execute(
                    """
                    SELECT endpoint_id FROM student_llm_preferences
                    WHERE user_id = %s AND household_id = %s
                    """,
                    (user_id, household_id),
                )
                preference = await cur.fetchone()
    default_id = (
        str(settings["default_endpoint_id"])
        if settings and settings["default_endpoint_id"]
        else None
    )
    preference_id = (
        str(preference["endpoint_id"])
        if preference and preference["endpoint_id"]
        else None
    )
    return {
        "household_id": str(household_id),
        "endpoints": [_student_endpoint_summary(row) for row in endpoints],
        "default": _student_endpoint_summary(endpoint_by_id.get(default_id))
        if default_id
        else None,
        "preference": _student_endpoint_summary(endpoint_by_id.get(preference_id))
        if preference_id
        else None,
        "_stale_preference": bool(
            preference_id and preference_id not in endpoint_by_id
        ),
    }


async def upsert_student_preference(
    user_id: str, household_id: str, endpoint_id: str | None
) -> dict[str, Any]:
    """Set a student's preference; composite FKs enforce household ownership."""
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                INSERT INTO student_llm_preferences (user_id, household_id, endpoint_id)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE
                SET household_id = EXCLUDED.household_id,
                    endpoint_id = EXCLUDED.endpoint_id,
                    updated_at = NOW()
                RETURNING user_id, household_id, endpoint_id, updated_at
                """,
                (user_id, household_id, endpoint_id),
            )
            row = await cur.fetchone()
    result = dict(
        row
        or {
            "user_id": user_id,
            "household_id": household_id,
            "endpoint_id": endpoint_id,
        }
    )
    result["household_id"] = str(result["household_id"])
    if result.get("endpoint_id") is not None:
        result["endpoint_id"] = str(result["endpoint_id"])
    return result


__all__ = [
    "API_KEY_UNSET",
    "FIELD_UNSET",
    "create_household_endpoint",
    "delete_household_endpoint",
    "get_endpoint_for_runtime",
    "get_household_availability",
    "list_household_endpoints",
    "set_household_default",
    "update_household_endpoint",
    "upsert_student_preference",
]
