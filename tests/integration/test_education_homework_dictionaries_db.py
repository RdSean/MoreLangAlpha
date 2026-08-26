"""Real PostgreSQL contracts for assembled K12 homework dictionaries."""

from contextlib import asynccontextmanager

import pytest

from src.server.database import education_homework


pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_homework_dictionaries_preserve_seeded_order_and_valid_subject_type_pairs(
    db_conn, monkeypatch
):
    @asynccontextmanager
    async def use_test_connection():
        yield db_conn

    monkeypatch.setattr(education_homework, "get_db_connection", use_test_connection)

    dictionaries = await education_homework.list_homework_dictionaries()

    assert [subject["code"] for subject in dictionaries["subjects"]] == [
        "chinese",
        "math",
        "english",
        "physics",
        "chemistry",
        "biology",
        "history",
        "geography",
        "politics",
    ]
    assert dictionaries["subjects"][0]["color"] == "#D95D39"
    assert dictionaries["subjects"][1]["color"] == "#277DA1"

    subject_types = {
        subject["code"]: [homework_type["code"] for homework_type in subject["homework_types"]]
        for subject in dictionaries["subjects"]
    }
    assert subject_types["chinese"] == [
        "preview",
        "practice",
        "read",
        "recite",
        "write",
        "review",
        "speak",
    ]
    assert subject_types["math"] == ["preview", "practice", "review", "research"]
    assert "listen" not in subject_types["math"]
    assert "grammar" not in subject_types["chinese"]

    assert [grade["code"] for grade in dictionaries["grade_levels"]] == [
        "g1",
        "g2",
        "g3",
        "g4",
        "g5",
        "g6",
        "g7",
        "g8",
        "g9",
        "g10",
        "g11",
        "g12",
    ]
    assert [source["code"] for source in dictionaries["practice_sources"]] == [
        "schoolwork",
        "homework",
    ]
