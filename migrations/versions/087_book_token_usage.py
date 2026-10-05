"""Preserve provider-reported usage without billing managed textbook runs."""

from migrations.textbook_ddl import execute_textbook_ddl as execute

revision = "087_book_token_usage"
down_revision = "086_book_timing_boundaries"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute("""ALTER TABLE education_book_job_attempts ADD COLUMN token_usage JSONB
      CHECK (token_usage IS NULL OR jsonb_typeof(token_usage)='object')""")


def downgrade() -> None:
    execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM education_book_job_attempts WHERE token_usage IS NOT NULL) THEN
        RAISE EXCEPTION '087 rollback requires explicit preservation of token usage';
      END IF;
    END $$;
    ALTER TABLE education_book_job_attempts DROP COLUMN token_usage""")
