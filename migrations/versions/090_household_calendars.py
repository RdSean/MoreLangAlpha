"""Persist household-shared ICS calendar sources."""

from alembic import op

revision = "090_household_calendars"
down_revision = "089_textbook_covers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE education_calendar_sources (
            source_id UUID PRIMARY KEY,
            household_id UUID NOT NULL REFERENCES education_households(household_id) ON DELETE CASCADE,
            created_by_user_id VARCHAR(255) REFERENCES users(user_id) ON DELETE SET NULL,
            name VARCHAR(255) NOT NULL CHECK (length(btrim(name)) > 0),
            filename VARCHAR(255) NOT NULL CHECK (length(btrim(filename)) > 0),
            filename_key VARCHAR(255) NOT NULL,
            content TEXT NOT NULL CHECK (octet_length(content) BETWEEN 1 AND 1048576),
            sha256 VARCHAR(64) NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
            event_count INTEGER NOT NULL CHECK (event_count BETWEEN 1 AND 500),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (household_id, filename_key),
            UNIQUE (household_id, sha256)
        );
        CREATE INDEX education_calendar_sources_household_updated_idx
            ON education_calendar_sources (household_id, updated_at DESC, source_id);
    """)


def downgrade() -> None:
    op.execute("DROP TABLE education_calendar_sources;")
