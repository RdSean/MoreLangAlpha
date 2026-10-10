"""Add a shared Pokemon card content catalog for future education rewards."""

from alembic import op

revision = "091_pokemon_cards"
down_revision = "090_household_calendars"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE education_pokemon_cards (
            card_id UUID PRIMARY KEY,
            source_card_id VARCHAR(128) NOT NULL UNIQUE
                CHECK (source_card_id ~ '^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$'),
            set_code TEXT NOT NULL CHECK (length(btrim(set_code)) > 0),
            series_name TEXT NOT NULL CHECK (length(btrim(series_name)) > 0),
            name TEXT NOT NULL CHECK (length(btrim(name)) > 0),
            category TEXT NOT NULL CHECK (length(btrim(category)) > 0),
            element TEXT NOT NULL DEFAULT '',
            hp INTEGER CHECK (hp > 0 AND hp <= 10000),
            stage TEXT NOT NULL DEFAULT '',
            card_number TEXT NOT NULL CHECK (length(btrim(card_number)) > 0),
            rarity TEXT NOT NULL DEFAULT '',
            illustrator TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '',
            source_image_path TEXT NOT NULL,
            image_bucket TEXT NOT NULL CHECK (length(btrim(image_bucket)) > 0),
            image_key TEXT NOT NULL UNIQUE,
            image_sha256 VARCHAR(64) NOT NULL CHECK (image_sha256 ~ '^[0-9a-f]{64}$'),
            image_content_type TEXT NOT NULL CHECK (image_content_type = 'image/png'),
            image_byte_size BIGINT NOT NULL CHECK (image_byte_size BETWEEN 1 AND 10485760),
            image_width INTEGER NOT NULL CHECK (image_width BETWEEN 1 AND 10000),
            image_height INTEGER NOT NULL CHECK (image_height BETWEEN 1 AND 10000),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CHECK (image_key = 'education/pokemon/cards/' || source_card_id || '/' || image_sha256 || '.png')
        );
        CREATE INDEX education_pokemon_cards_set_idx
            ON education_pokemon_cards (set_code, source_card_id);
    """)


def downgrade() -> None:
    op.execute("DROP TABLE education_pokemon_cards;")
