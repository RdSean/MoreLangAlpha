"""Contracts for the mode-filtered skills listing endpoint."""

import pytest

from src.server.app.skills import get_skills


@pytest.mark.asyncio
async def test_native_book_learning_skills_are_listed_for_ptc_but_not_flash():
    """PTC-only book skills must never enter the Flash slash-command source."""
    ptc = await get_skills(mode="ptc")
    flash = await get_skills(mode="flash")

    ptc_commands = {skill["command"] for skill in ptc["skills"]}
    flash_names = {skill["name"] for skill in flash["skills"]}

    assert "book-to-skill" in ptc_commands
    assert "the-knowledge-guy" in ptc_commands
    assert "book-to-skill" not in flash_names
    assert "the-knowledge-guy" not in flash_names
