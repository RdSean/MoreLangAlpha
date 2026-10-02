"""Contracts for the mode-filtered skills listing endpoint."""

import pytest

from src.server.app.skills import get_skills


@pytest.mark.asyncio
async def test_native_book_learning_skills_are_listed_for_ptc_but_not_flash():
    """PTC-only book skills must never enter the Flash slash-command source."""
    # Called directly rather than through the router, so every ``Query``
    # default has to be spelled out: an unresolved ``Query`` object is truthy
    # and would take the workspace branch by accident. ``user_id=None`` is the
    # anonymous view — the platform tier, which is where these two bundle
    # skills live. The own-tier rows need a database and are not this contract.
    ptc = await get_skills(
        user_id=None,
        mode="ptc",
        include_disabled=False,
        workspace_id=None,
        all_scopes=False,
    )
    flash = await get_skills(
        user_id=None,
        mode="flash",
        include_disabled=False,
        workspace_id=None,
        all_scopes=False,
    )

    ptc_commands = {skill.command for skill in ptc["skills"]}
    flash_names = {skill.name for skill in flash["skills"]}

    assert "book-to-skill" not in ptc_commands
    assert "more-to-skills" in ptc_commands
    assert "book-to-skill" not in flash_names
    assert "more-to-skills" not in flash_names
