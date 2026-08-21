"""PostgreSQL persistence for local credentials and opaque sessions."""

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from psycopg.errors import UniqueViolation
from psycopg.rows import dict_row

from src.server.database.pool import get_db_connection


class AccountAlreadyExistsError(ValueError):
    """The normalized email or username already belongs to an account."""


class ParentMembershipRequiredError(PermissionError):
    """The requester is not a parent in any household."""


def normalize_login_identifier(value: str) -> str:
    """Normalize identifiers once so uniqueness and login use the same representation."""
    return value.strip().casefold()


def _member_from_row(row: dict[str, Any]) -> dict[str, Any]:
    member = {
        "user_id": row["user_id"],
        "email": row["email"],
        "name": row["display_name"],
        "role": row["role"],
        "household_id": str(row["household_id"]),
    }
    if row.get("login_identifier"):
        member["username"] = row["login_identifier"]
    return member


async def register_parent_account(
    *,
    email: str,
    password_hash: str,
    name: str,
    household_name: str,
    timezone_name: str,
) -> dict[str, Any]:
    """Create the parent account, household, and first membership atomically."""
    user_id = str(uuid4())
    household_id = str(uuid4())
    login_identifier = normalize_login_identifier(email)

    try:
        async with get_db_connection() as conn:
            async with conn.transaction():
                async with conn.cursor(row_factory=dict_row) as cur:
                    await cur.execute(
                        """
                        INSERT INTO users (
                            user_id, email, name, timezone, auth_provider,
                            onboarding_completed, created_at, updated_at
                        )
                        VALUES (%s, %s, %s, %s, 'local', FALSE, NOW(), NOW())
                        """,
                        (user_id, email, name, timezone_name),
                    )
                    await cur.execute(
                        """
                        INSERT INTO user_preferences (
                            user_preference_id, user_id, created_at, updated_at
                        )
                        VALUES (gen_random_uuid(), %s, NOW(), NOW())
                        """,
                        (user_id,),
                    )
                    await cur.execute(
                        """
                        INSERT INTO local_auth_accounts (
                            user_id, login_identifier, email, password_hash,
                            is_active, created_at, updated_at
                        )
                        VALUES (%s, %s, %s, %s, TRUE, NOW(), NOW())
                        """,
                        (user_id, login_identifier, email, password_hash),
                    )
                    await cur.execute(
                        """
                        INSERT INTO education_households (
                            household_id, name, timezone, model_owner_user_id,
                            created_at, updated_at
                        )
                        VALUES (%s, %s, %s, %s, NOW(), NOW())
                        """,
                        (household_id, household_name, timezone_name, user_id),
                    )
                    await cur.execute(
                        """
                        INSERT INTO education_memberships (
                            household_id, user_id, role, display_name, created_at, updated_at
                        )
                        VALUES (%s, %s, 'parent', %s, NOW(), NOW())
                        """,
                        (household_id, user_id, name),
                    )
    except UniqueViolation as exc:
        raise AccountAlreadyExistsError("An account already uses this email or username") from exc

    return {
        "user_id": user_id,
        "email": email,
        "name": name,
        "role": "parent",
        "household_id": household_id,
    }


async def create_child_account(
    *,
    parent_user_id: str,
    username: str,
    password_hash: str,
    name: str,
) -> dict[str, Any]:
    """Create a student only after locking and validating the parent's membership."""
    user_id = str(uuid4())
    login_identifier = normalize_login_identifier(username)

    try:
        async with get_db_connection() as conn:
            async with conn.transaction():
                async with conn.cursor(row_factory=dict_row) as cur:
                    await cur.execute(
                        """
                        SELECT household_id
                        FROM education_memberships
                        WHERE user_id = %s AND role = 'parent'
                        ORDER BY created_at ASC
                        LIMIT 1
                        FOR UPDATE
                        """,
                        (parent_user_id,),
                    )
                    parent_membership = await cur.fetchone()
                    if not parent_membership:
                        raise ParentMembershipRequiredError("Only a parent can create child accounts")
                    household_id = str(parent_membership["household_id"])

                    await cur.execute(
                        """
                        INSERT INTO users (
                            user_id, name, auth_provider, onboarding_completed, created_at, updated_at
                        )
                        VALUES (%s, %s, 'local', FALSE, NOW(), NOW())
                        """,
                        (user_id, name),
                    )
                    await cur.execute(
                        """
                        INSERT INTO user_preferences (
                            user_preference_id, user_id, created_at, updated_at
                        )
                        VALUES (gen_random_uuid(), %s, NOW(), NOW())
                        """,
                        (user_id,),
                    )
                    await cur.execute(
                        """
                        INSERT INTO local_auth_accounts (
                            user_id, login_identifier, password_hash, is_active, created_at, updated_at
                        )
                        VALUES (%s, %s, %s, TRUE, NOW(), NOW())
                        """,
                        (user_id, login_identifier, password_hash),
                    )
                    await cur.execute(
                        """
                        INSERT INTO education_memberships (
                            household_id, user_id, role, display_name, created_at, updated_at
                        )
                        VALUES (%s, %s, 'student', %s, NOW(), NOW())
                        """,
                        (household_id, user_id, name),
                    )
    except UniqueViolation as exc:
        raise AccountAlreadyExistsError("An account already uses this email or username") from exc

    return {
        "user_id": user_id,
        "email": None,
        "name": name,
        "role": "student",
        "household_id": household_id,
    }


async def get_account_for_login(login_identifier: str) -> dict[str, Any] | None:
    """Fetch one active local account and its earliest household membership."""
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT
                    accounts.user_id, accounts.password_hash, accounts.is_active,
                    users.email, memberships.household_id, memberships.role,
                    memberships.display_name
                FROM local_auth_accounts AS accounts
                JOIN users ON users.user_id = accounts.user_id
                JOIN LATERAL (
                    SELECT household_id, role, display_name
                    FROM education_memberships
                    WHERE user_id = accounts.user_id
                    ORDER BY created_at ASC
                    LIMIT 1
                ) AS memberships ON TRUE
                WHERE accounts.login_identifier = %s AND accounts.is_active = TRUE
                """,
                (normalize_login_identifier(login_identifier),),
            )
            row = await cur.fetchone()
    return dict(row) if row else None


async def get_member_for_user(user_id: str) -> dict[str, Any] | None:
    """Return the member profile used by the auth API's ``/me`` response."""
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT users.user_id, users.email, memberships.household_id,
                       memberships.role, memberships.display_name,
                       accounts.login_identifier
                FROM education_memberships AS memberships
                JOIN users ON users.user_id = memberships.user_id
                LEFT JOIN local_auth_accounts AS accounts ON accounts.user_id = memberships.user_id
                WHERE memberships.user_id = %s
                ORDER BY memberships.created_at ASC
                LIMIT 1
                """,
                (user_id,),
            )
            row = await cur.fetchone()
    return _member_from_row(dict(row)) if row else None


async def list_household_members_for_parent(parent_user_id: str) -> list[dict[str, Any]]:
    """List a parent's household members; non-parents receive no household data."""
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT household_id
                FROM education_memberships
                WHERE user_id = %s AND role = 'parent'
                ORDER BY created_at ASC
                LIMIT 1
                """,
                (parent_user_id,),
            )
            membership = await cur.fetchone()
            if not membership:
                raise ParentMembershipRequiredError("Only a parent can view household members")
            await cur.execute(
                """
                SELECT users.user_id, users.email, memberships.household_id,
                       memberships.role, memberships.display_name,
                       accounts.login_identifier
                FROM education_memberships AS memberships
                JOIN users ON users.user_id = memberships.user_id
                LEFT JOIN local_auth_accounts AS accounts ON accounts.user_id = memberships.user_id
                WHERE memberships.household_id = %s
                ORDER BY memberships.role ASC, memberships.created_at ASC
                """,
                (membership["household_id"],),
            )
            rows = await cur.fetchall()
    return [_member_from_row(dict(row)) for row in rows]


async def create_session_record(
    *, user_id: str, token_digest: str, expires_at: datetime
) -> None:
    """Store one session digest; callers retain the original browser token only."""
    async with get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO local_auth_sessions (
                    session_id, user_id, token_digest, expires_at, created_at, last_seen_at
                )
                VALUES (%s, %s, %s, %s, NOW(), NOW())
                """,
                (str(uuid4()), user_id, token_digest, expires_at),
            )


async def get_user_id_for_session_digest(token_digest: str) -> str | None:
    """Resolve an unrevoked, unexpired session digest to its durable user ID."""
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT user_id
                FROM local_auth_sessions
                WHERE token_digest = %s AND revoked_at IS NULL AND expires_at > NOW()
                """,
                (token_digest,),
            )
            row = await cur.fetchone()
    return row["user_id"] if row else None


async def revoke_session_digest(token_digest: str) -> bool:
    """Revoke one session, returning whether it was active before this call."""
    async with get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                UPDATE local_auth_sessions
                SET revoked_at = NOW()
                WHERE token_digest = %s AND revoked_at IS NULL
                """,
                (token_digest,),
            )
            return cur.rowcount == 1


async def rotate_session_record(
    *, old_token_digest: str, new_token_digest: str, expires_at: datetime
) -> str | None:
    """Atomically replace an active session and return its owner, if still valid."""
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    SELECT session_id, user_id
                    FROM local_auth_sessions
                    WHERE token_digest = %s AND revoked_at IS NULL AND expires_at > NOW()
                    FOR UPDATE
                    """,
                    (old_token_digest,),
                )
                session = await cur.fetchone()
                if not session:
                    return None
                new_session_id = str(uuid4())
                await cur.execute(
                    """
                    INSERT INTO local_auth_sessions (
                        session_id, user_id, token_digest, expires_at, created_at, last_seen_at
                    )
                    VALUES (%s, %s, %s, %s, NOW(), NOW())
                    """,
                    (new_session_id, session["user_id"], new_token_digest, expires_at),
                )
                await cur.execute(
                    """
                    UPDATE local_auth_sessions
                    SET revoked_at = NOW(), replaced_by_session_id = %s
                    WHERE session_id = %s
                    """,
                    (new_session_id, session["session_id"]),
                )
    return session["user_id"]


def session_expiry(ttl: timedelta) -> datetime:
    """Return an aware expiration stamp for storage in PostgreSQL."""
    return datetime.now(timezone.utc) + ttl
