"""Unit tests for opaque local-auth session primitives."""

from src.server.auth.local_sessions import (
    SESSION_COOKIE_NAME,
    hash_password,
    hash_session_token,
    new_session_token,
    verify_password,
)


def test_password_hash_round_trip_uses_argon2id():
    password_hash = hash_password("correct horse battery staple")

    assert password_hash.startswith("$argon2id$")
    assert verify_password("correct horse battery staple", password_hash) is True
    assert verify_password("incorrect", password_hash) is False


def test_opaque_session_token_is_random_and_only_digest_is_storable():
    first = new_session_token()
    second = new_session_token()

    assert first != second
    assert len(first) >= 32
    assert hash_session_token(first) != first
    assert hash_session_token(first) == hash_session_token(first)


def test_session_cookie_name_is_stable():
    assert SESSION_COOKIE_NAME == "langalpha_session"
