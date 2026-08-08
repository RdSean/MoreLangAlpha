"""Password and opaque-session helpers for first-party local accounts."""

import hashlib
import secrets
from datetime import timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from argon2.low_level import Type

from src.config.env import AUTH_COOKIE_SECURE, LOCAL_AUTH_SESSION_TTL_DAYS

SESSION_COOKIE_NAME = "langalpha_session"
_PASSWORD_HASHER = PasswordHasher(type=Type.ID)


def hash_password(password: str) -> str:
    """Return an Argon2id password hash; plaintext passwords never reach storage."""
    return _PASSWORD_HASHER.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Return whether ``password`` verifies against an Argon2id hash."""
    try:
        return _PASSWORD_HASHER.verify(password_hash, password)
    except (InvalidHashError, VerificationError):
        return False


def new_session_token() -> str:
    """Create a browser-held bearer secret that is never stored verbatim."""
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    """Return the fixed-length database digest for an opaque session token."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def session_ttl() -> timedelta:
    """Return the configured absolute session lifetime."""
    return timedelta(days=LOCAL_AUTH_SESSION_TTL_DAYS)


def session_cookie_options() -> dict[str, object]:
    """Cookie flags shared by login, rotation, and logout responses."""
    return {
        "httponly": True,
        "secure": AUTH_COOKIE_SECURE,
        "samesite": "lax",
        "max_age": int(session_ttl().total_seconds()),
        "path": "/",
    }


async def get_user_id_for_session_token(token: str) -> str | None:
    """Resolve a browser token through its digest without exposing stored values."""
    from src.server.database.auth_accounts import get_user_id_for_session_digest

    return await get_user_id_for_session_digest(hash_session_token(token))
