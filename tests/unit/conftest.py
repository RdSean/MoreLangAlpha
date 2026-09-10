"""Socket tripwire: unit tests must not reach real network endpoints.

A mock that silently stops intercepting (e.g. after a module move breaks a
patch target) fails OPEN — the test goes green against live I/O. Blocking
socket creation turns that failure mode into a loud error. AF_UNIX stays
allowed: asyncio's event loop self-pipe is a unix socketpair.
"""

from unittest.mock import AsyncMock

import pytest
import pytest_socket


@pytest.fixture(autouse=True)
def _no_real_sockets(request):
    if request.node.get_closest_marker("enable_socket"):
        yield
        return
    pytest_socket.disable_socket(allow_unix_socket=True)
    yield
    pytest_socket.enable_socket()


@pytest.fixture(autouse=True)
def _reader_pool_follows_cache_client(monkeypatch):
    """Alias the dedicated stream-reader pool onto the injected cache client.

    Blocking XREADs moved off the cache pool in production, but unit tests
    inject their fakes through ``get_cache_client``. Without this the readers
    would build a real ``BlockingConnectionPool`` and block inside XREAD; the
    accessor deliberately has no cache fallback of its own.

    One seam, and it follows whichever client the caller resolved, because the
    accessor is handed that client rather than looking one up. A test wanting
    real reader-pool behavior overrides this single symbol.
    """
    from src.utils.cache import stream_pool

    async def _reader(cache):
        return getattr(cache, "client", None)

    monkeypatch.setattr(stream_pool, "get_stream_reader_client", _reader)


@pytest.fixture(autouse=True)
def _default_education_membership(monkeypatch):
    """Keep synthetic unit-test users outside a household unless a test opts in."""
    from src.server.services import education_access

    monkeypatch.setattr(
        education_access,
        "get_membership_for_user",
        AsyncMock(return_value=None),
    )


@pytest.fixture(scope="session")
def shipped_skill_md():
    """Locate a shipped skill's SKILL.md on disk, by name.

    A registry entry's ``skill_md_path`` is where the *agent* reaches the file
    inside a sandbox, not where this repo keeps it: the shipped skills live in
    the bundle that declares them, and the sync flattens every source into one
    directory. Joining that suffix onto the repo root reads as correct and is
    not, so the lookup asks the bundles instead.
    """
    from pathlib import Path

    from ptc_agent.config.plugins import bundled_skill_dirs

    def find(name: str) -> Path:
        for root in bundled_skill_dirs():
            candidate = root / name / "SKILL.md"
            if candidate.is_file():
                return candidate
        raise AssertionError(f"no bundle ships a {name!r} skill")

    return find
