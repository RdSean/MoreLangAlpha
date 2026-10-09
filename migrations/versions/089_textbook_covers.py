"""Add optional household textbook cover metadata."""

from alembic import op


revision = "089_textbook_covers"
down_revision = "088_book_reading_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE education_textbooks
          ADD COLUMN cover_storage_key TEXT,
          ADD COLUMN cover_filename VARCHAR(255),
          ADD COLUMN cover_content_type VARCHAR(64),
          ADD COLUMN cover_size_bytes BIGINT,
          ADD COLUMN cover_sha256 VARCHAR(64),
          ADD COLUMN cover_updated_at TIMESTAMPTZ;
        ALTER TABLE education_textbooks
          ADD CONSTRAINT textbook_cover_metadata_complete CHECK (
            (cover_storage_key IS NULL AND cover_filename IS NULL
             AND cover_content_type IS NULL AND cover_size_bytes IS NULL
             AND cover_sha256 IS NULL AND cover_updated_at IS NULL)
            OR
            (cover_storage_key LIKE 'education/' || household_id::text
             || '/textbooks/' || textbook_id::text || '/cover/%'
             AND cover_filename IS NOT NULL AND length(btrim(cover_filename)) > 0
             AND cover_content_type IN ('image/png', 'image/jpeg', 'image/webp')
             AND cover_size_bytes > 0 AND cover_size_bytes <= 10485760
             AND cover_sha256 ~ '^[0-9a-f]{64}$'
             AND cover_updated_at IS NOT NULL)
          );
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE education_textbooks
          DROP CONSTRAINT textbook_cover_metadata_complete,
          DROP COLUMN cover_updated_at,
          DROP COLUMN cover_sha256,
          DROP COLUMN cover_size_bytes,
          DROP COLUMN cover_content_type,
          DROP COLUMN cover_filename,
          DROP COLUMN cover_storage_key;
    """)
