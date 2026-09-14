"""Record what each document conversion cost.

The Usage surface needs pages processed and money spent per document, by day.
That could have been dug back out of the parsers' artifact metadata, but the
metadata shape is per-provider by design, so the page would end up parsing a
different blob per parser. A row per job is the shape the page actually asks
for.

``UNIQUE (job_id)`` is the load-bearing part. Parse jobs are retried
(``document_parse_jobs.attempt_count`` exists for exactly that), and a record
keyed on the job is what keeps a retry from counting the same spend twice —
the writer upserts, so the row always describes the job rather than the most
recent attempt.

Scoped by ``owner_user_id`` because every read is: the page shows what *this*
account's documents cost, not what the deployment spent, which would leak other
households' activity on a shared deployment.
"""

from __future__ import annotations

from alembic import op


revision = "061_document_usage_records"
down_revision = "060_restore_finance_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE document_usage_records (
            record_id VARCHAR(16) PRIMARY KEY
                CHECK (record_id ~ '^use-[0-9A-Za-z]{12}$'),
            job_id VARCHAR(16) NOT NULL
                REFERENCES document_parse_jobs(job_id) ON DELETE CASCADE,
            owner_user_id VARCHAR(255) NOT NULL
                REFERENCES users(user_id) ON DELETE RESTRICT,
            provider_id VARCHAR(100) NOT NULL,
            pages INTEGER NOT NULL CHECK (pages >= 0),
            list_cost_cents INTEGER CHECK (list_cost_cents >= 0),
            final_cost_cents INTEGER NOT NULL CHECK (final_cost_cents >= 0),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (job_id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX idx_document_usage_owner_created
        ON document_usage_records (owner_user_id, created_at DESC)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_document_usage_owner_created")
    op.execute("DROP TABLE IF EXISTS document_usage_records")
