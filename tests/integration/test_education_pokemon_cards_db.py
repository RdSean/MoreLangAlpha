import asyncio
from uuid import uuid4

import pytest
from psycopg.errors import CheckViolation

from src.server.database.education_pokemon_cards import (
    check_catalog_schema,
    get_pokemon_card,
    list_pokemon_cards,
    upsert_pokemon_cards,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def record(source_id="test-001"):
    digest = "a" * 64
    return dict(
        source_card_id=source_id,
        set_code="test",
        series_name="Test",
        name="Pikachu",
        category="Pokemon",
        element="Electric",
        hp=60,
        stage="Basic",
        card_number="001",
        rarity="Rare",
        illustrator="Artist",
        notes="",
        source_image_path="test/test-001.png",
        image_bucket="cards",
        image_key=f"education/pokemon/cards/{source_id}/{digest}.png",
        image_sha256=digest,
        image_content_type="image/png",
        image_byte_size=200,
        image_width=64,
        image_height=88,
    )


async def test_catalog_upsert_preserves_id_and_unchanged_timestamp(
    db_conn, patched_get_db_connection
):
    await check_catalog_schema()
    first = record()
    assert await upsert_pokemon_cards([first]) == 1
    before = await (
        await db_conn.execute(
            "SELECT card_id, updated_at FROM education_pokemon_cards WHERE source_card_id = 'test-001'"
        )
    ).fetchone()
    assert await upsert_pokemon_cards([first]) == 0
    after = await (
        await db_conn.execute(
            "SELECT card_id, updated_at FROM education_pokemon_cards WHERE source_card_id = 'test-001'"
        )
    ).fetchone()
    assert before == after
    assert await upsert_pokemon_cards([{**first, "notes": "Updated note"}]) == 1
    updated = await (
        await db_conn.execute(
            "SELECT card_id, notes FROM education_pokemon_cards WHERE source_card_id = 'test-001'"
        )
    ).fetchone()
    assert updated["card_id"] == before["card_id"]
    assert updated["notes"] == "Updated note"


async def test_catalog_batch_rolls_back_and_rejects_non_catalog_objects(
    db_conn, patched_get_db_connection
):
    with pytest.raises(CheckViolation):
        await upsert_pokemon_cards(
            [
                record("test-002"),
                {**record("test-003"), "image_key": "unrelated/image.png"},
            ]
        )
    count = await (
        await db_conn.execute(
            "SELECT count(*) AS n FROM education_pokemon_cards WHERE source_card_id IN ('test-002','test-003')"
        )
    ).fetchone()
    assert count["n"] == 0


async def test_catalog_pages_in_numeric_order_and_filters_sets(
    db_conn, patched_get_db_connection
):
    await db_conn.execute("TRUNCATE education_pokemon_cards")
    await upsert_pokemon_cards(
        [record(f"test-{n}") for n in (10, 1, 2)]
        + [{**record("other-1"), "set_code": "other", "series_name": "Other"}]
    )
    first = await list_pokemon_cards(page=1, page_size=2, set_code="test")
    assert [item["source_card_id"] for item in first["items"]] == ["test-1", "test-2"]
    assert first["total"] == 3
    assert len(first["series"]) == 2
    last = await list_pokemon_cards(page=999, page_size=2, set_code="test")
    assert last["page"] == 2
    assert [item["source_card_id"] for item in last["items"]] == ["test-10"]
    assert (await get_pokemon_card(str(first["items"][0]["card_id"])))[
        "image_key"
    ] == first["items"][0]["image_key"]
    assert await get_pokemon_card(str(uuid4())) is None
    empty = await list_pokemon_cards(page=999, page_size=20, set_code="missing")
    assert empty["items"] == [] and empty["total"] == 0 and empty["page"] == 1
    assert (await list_pokemon_cards(page=1, page_size=20, set_code=None))["total"] == 4


async def test_migration_roundtrip_preserves_existing_family_calendar(
    db_conn, test_db_uri
):
    from alembic import command
    from alembic.config import Config

    parent = f"card-migration-{uuid4()}"
    household, source = uuid4(), uuid4()
    async with db_conn.transaction():
        await db_conn.execute(
            "INSERT INTO users (user_id, name) VALUES (%s,'Parent')", (parent,)
        )
        await db_conn.execute(
            "INSERT INTO education_households (household_id,name,model_owner_user_id) VALUES (%s,'Family',%s)",
            (household, parent),
        )
        await db_conn.execute(
            "INSERT INTO education_memberships (household_id,user_id,role,display_name) VALUES (%s,%s,'parent','Parent')",
            (household, parent),
        )
    await db_conn.execute(
        "INSERT INTO education_calendar_sources (source_id,household_id,name,filename,filename_key,content,sha256,event_count) VALUES (%s,%s,'Classes','classes.ics','classes.ics','Calendar',%s,1)",
        (source, household, "b" * 64),
    )
    cfg = Config("alembic.ini")
    cfg.set_main_option(
        "sqlalchemy.url",
        test_db_uri.replace("postgresql://", "postgresql+psycopg://", 1),
    )
    await asyncio.to_thread(command.downgrade, cfg, "090_household_calendars")
    assert (
        await (
            await db_conn.execute("SELECT to_regclass('education_pokemon_cards') AS t")
        ).fetchone()
    )["t"] is None
    await asyncio.to_thread(command.upgrade, cfg, "head")
    assert (
        await (
            await db_conn.execute(
                "SELECT name FROM education_calendar_sources WHERE source_id=%s",
                (source,),
            )
        ).fetchone()
    )["name"] == "Classes"
    assert (
        await (
            await db_conn.execute("SELECT version_num FROM alembic_version")
        ).fetchone()
    )["version_num"] == "091_pokemon_cards"
