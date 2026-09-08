"""Add monotone in-flight credit ledgers to root and subagent runs.

Semantic port of origin/main ``033_in_flight_credits``. The additive columns
remain nullable only where the remote contract requires it; pre-gate rows are
therefore safe during rolling deployment.
"""

from alembic import op


revision = "052_in_flight_credits"
down_revision = "051_account_disable_kind"
branch_labels = None
depends_on = None

_RESPONSES_INDEX = "ix_responses_in_flight_by_user"
_SUBAGENT_INDEX = "ix_subagent_runs_in_flight_by_user"
_SUBAGENT_SETTLED_INDEX = "ix_subagent_runs_settled_by_parent"


def upgrade() -> None:
    for table in ("conversation_responses", "subagent_runs"):
        with op.get_context().autocommit_block():
            op.execute("SET lock_timeout = '5s'")
            op.execute(
                f"""
                ALTER TABLE {table}
                    ADD COLUMN IF NOT EXISTS in_flight_credits NUMERIC NOT NULL DEFAULT 0,
                    ADD COLUMN IF NOT EXISTS user_id VARCHAR(255),
                    ADD COLUMN IF NOT EXISTS usage_settled_at TIMESTAMPTZ
                """
            )

    with op.get_context().autocommit_block():
        op.execute("SET lock_timeout = '5s'")
        for table in ("conversation_responses", "subagent_runs"):
            constraint = f"ck_{table}_in_flight_credits_nonneg"
            op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {constraint}")
            op.execute(
                f"""ALTER TABLE {table}
                    ADD CONSTRAINT {constraint}
                    CHECK (in_flight_credits >= 0) NOT VALID"""
            )
        op.execute("SET lock_timeout = 0")
        for table in ("conversation_responses", "subagent_runs"):
            constraint = f"ck_{table}_in_flight_credits_nonneg"
            op.execute(f"ALTER TABLE {table} VALIDATE CONSTRAINT {constraint}")

        op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {_RESPONSES_INDEX}")
        op.execute(
            f"""CREATE INDEX CONCURRENTLY {_RESPONSES_INDEX}
                ON conversation_responses (user_id)
                INCLUDE (in_flight_credits)
                WHERE usage_settled_at IS NULL AND in_flight_credits > 0
                  AND user_id IS NOT NULL"""
        )
        op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {_SUBAGENT_INDEX}")
        op.execute(
            f"""CREATE INDEX CONCURRENTLY {_SUBAGENT_INDEX}
                ON subagent_runs (user_id)
                INCLUDE (in_flight_credits, parent_run_id)
                WHERE usage_settled_at IS NULL AND in_flight_credits > 0
                  AND user_id IS NOT NULL"""
        )
        op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {_SUBAGENT_SETTLED_INDEX}")
        op.execute(
            f"""CREATE INDEX CONCURRENTLY {_SUBAGENT_SETTLED_INDEX}
                ON subagent_runs (parent_run_id)
                INCLUDE (in_flight_credits, user_id)
                WHERE usage_settled_at IS NOT NULL AND in_flight_credits > 0"""
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("SET lock_timeout = 0")
        op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {_SUBAGENT_SETTLED_INDEX}")
        op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {_SUBAGENT_INDEX}")
        op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {_RESPONSES_INDEX}")

    for table in ("subagent_runs", "conversation_responses"):
        with op.get_context().autocommit_block():
            op.execute("SET lock_timeout = '5s'")
            constraint = f"ck_{table}_in_flight_credits_nonneg"
            op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {constraint}")
            op.execute(
                f"""ALTER TABLE {table}
                    DROP COLUMN IF EXISTS usage_settled_at,
                    DROP COLUMN IF EXISTS user_id,
                    DROP COLUMN IF EXISTS in_flight_credits"""
            )
