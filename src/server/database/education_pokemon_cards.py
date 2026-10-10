"""Shared Pokemon card catalog persistence, independent of reward mechanics."""

from collections.abc import Mapping, Sequence
from uuid import uuid4

from psycopg import sql
from psycopg.rows import dict_row

from src.server.database.pool import get_db_connection

CARD_COLUMNS = (
    "source_card_id",
    "set_code",
    "series_name",
    "name",
    "category",
    "element",
    "hp",
    "stage",
    "card_number",
    "rarity",
    "illustrator",
    "notes",
    "source_image_path",
    "image_bucket",
    "image_key",
    "image_sha256",
    "image_content_type",
    "image_byte_size",
    "image_width",
    "image_height",
)


async def list_pokemon_cards(
    *, page: int, page_size: int, set_code: str | None
) -> dict:
    """Return a bounded page in numeric card order, with all available series."""
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT set_code, series_name, count(*) AS total "
                "FROM education_pokemon_cards GROUP BY set_code, series_name "
                "ORDER BY set_code, series_name"
            )
            series = await cur.fetchall()
            total = sum(
                row["total"]
                for row in series
                if set_code is None or row["set_code"] == set_code
            )
            page = min(page, max(1, (total + page_size - 1) // page_size))
            await cur.execute(
                """SELECT * FROM education_pokemon_cards
                   WHERE (%s::text IS NULL OR set_code = %s)
                   ORDER BY set_code,
                            substring(source_card_id FROM '-([0-9]+)')::numeric NULLS LAST,
                            source_card_id
                   LIMIT %s OFFSET %s""",
                (set_code, set_code, page_size, (page - 1) * page_size),
            )
            return {
                "items": await cur.fetchall(),
                "total": total,
                "page": page,
                "page_size": page_size,
                "series": series,
            }


async def get_pokemon_card(card_id: str) -> dict | None:
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT * FROM education_pokemon_cards WHERE card_id = %s", (card_id,)
            )
            return await cur.fetchone()


async def check_catalog_schema() -> None:
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT to_regclass('education_pokemon_cards') AS table_name"
            )
            if (await cur.fetchone())["table_name"] is None:
                raise RuntimeError("Apply migration 091_pokemon_cards before importing")


async def upsert_pokemon_cards(records: Sequence[Mapping[str, object]]) -> int:
    """Atomically import metadata; unchanged cards retain IDs and timestamps."""
    if not records:
        return 0
    mutable = CARD_COLUMNS[1:]
    identifiers = sql.SQL(", ").join(map(sql.Identifier, ("card_id", *CARD_COLUMNS)))
    assignments = sql.SQL(", ").join(
        sql.SQL("{0} = EXCLUDED.{0}").format(sql.Identifier(column))
        for column in mutable
    )
    current = sql.SQL(", ").join(
        sql.SQL("education_pokemon_cards.{}").format(sql.Identifier(column))
        for column in mutable
    )
    incoming = sql.SQL(", ").join(
        sql.SQL("EXCLUDED.{}").format(sql.Identifier(column)) for column in mutable
    )
    statement = sql.SQL("""
        INSERT INTO education_pokemon_cards ({columns}) VALUES ({values})
        ON CONFLICT (source_card_id) DO UPDATE SET {assignments}, updated_at = NOW()
        WHERE ({current}) IS DISTINCT FROM ({incoming})
    """).format(
        columns=identifiers,
        values=sql.SQL(", ").join(
            sql.Placeholder() for _ in range(len(CARD_COLUMNS) + 1)
        ),
        assignments=assignments,
        current=current,
        incoming=incoming,
    )
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor() as cur:
                await cur.executemany(
                    statement,
                    [
                        (uuid4(), *(row[column] for column in CARD_COLUMNS))
                        for row in records
                    ],
                )
                return cur.rowcount
