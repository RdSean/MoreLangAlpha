"""Restore the finance and insight schema the local baseline had dropped.

The local branch forked from upstream and then edited ``001_initial_schema.py``
to leave out everything that only served the finance surface: the
``risk_preference`` / ``investment_preference`` columns on ``user_preferences``
and the ``watchlists``, ``watchlist_items``, ``user_portfolios`` and
``market_insights`` tables. Local ``005`` and ``007`` were reduced to empty
stubs the same day, kept only so the revision chain stayed contiguous.

Merging the upstream platform core back brings the readers of that schema with
it — ``database/user.py`` selects the two preference columns on every turn, and
``/api/v1/watchlist``, the portfolio routes and the insights service read the
four tables. So the schema comes back, recreated from upstream's ``001`` with
the two changes that later revisions applied folded in, because those revisions
have already run here and cannot run again: ``005``'s partial unique index on
``market_insights (user_id) WHERE status = 'generating'``, and ``007``'s
``user_id`` UUID → VARCHAR conversion.

Deliberately excluded from here, because their local counterparts are *not*
empty: ``002_add_price_trigger_type`` (present locally as its own migration) and
``036_brokerage_capabilities`` (landed here as ``057``).

Revision ID: 060
Revises: 059
"""

from alembic import op
from sqlalchemy import text


revision = "060_restore_finance_schema"
down_revision = "059_direct_tools"
branch_labels = None
depends_on = None

_TABLES = ("watchlists", "watchlist_items", "user_portfolios", "market_insights")

# Anything a downgrade would silently destroy. Both preference columns are
# counted only when they hold more than the empty object the DDL defaults to.
_DATA_SQL = " UNION ALL ".join(
    f"SELECT '{table}' AS source, count(*) AS rows FROM {table}" for table in _TABLES
) + """
    UNION ALL
    SELECT 'user_preferences.risk_preference', count(*) FROM user_preferences
     WHERE COALESCE(risk_preference, '{}'::jsonb) <> '{}'::jsonb
    UNION ALL
    SELECT 'user_preferences.investment_preference', count(*) FROM user_preferences
     WHERE COALESCE(investment_preference, '{}'::jsonb) <> '{}'::jsonb
"""


def upgrade() -> None:
    # -- user_preferences: the two buckets the finance settings wrote into --
    op.execute("""
        ALTER TABLE user_preferences
            ADD COLUMN IF NOT EXISTS risk_preference JSONB DEFAULT '{}'::jsonb,
            ADD COLUMN IF NOT EXISTS investment_preference JSONB DEFAULT '{}'::jsonb
    """)

    # -- watchlists --
    op.execute("""
        CREATE TABLE IF NOT EXISTS watchlists (
            watchlist_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id VARCHAR(255) NOT NULL
                REFERENCES users(user_id) ON DELETE CASCADE,
            name VARCHAR(100) NOT NULL,
            description TEXT,
            is_default BOOLEAN NOT NULL DEFAULT FALSE,
            display_order INTEGER DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT unique_user_watchlist_name UNIQUE (user_id, name)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_watchlists_user_id ON watchlists(user_id)")

    # -- watchlist_items --
    op.execute("""
        CREATE TABLE IF NOT EXISTS watchlist_items (
            watchlist_item_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            watchlist_id UUID NOT NULL
                REFERENCES watchlists(watchlist_id) ON DELETE CASCADE,
            user_id VARCHAR(255) NOT NULL
                REFERENCES users(user_id) ON DELETE CASCADE,
            symbol VARCHAR(50) NOT NULL,
            instrument_type VARCHAR(30) NOT NULL,
            exchange VARCHAR(50),
            name VARCHAR(255),
            notes TEXT,
            alert_settings JSONB DEFAULT '{}'::jsonb,
            metadata JSONB DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT unique_watchlist_item
                UNIQUE (watchlist_id, symbol, instrument_type)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_watchlist_items_watchlist_id ON watchlist_items(watchlist_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_watchlist_items_user_id ON watchlist_items(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_watchlist_items_symbol ON watchlist_items(symbol)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_watchlist_items_user_symbol "
        "ON watchlist_items(user_id, symbol, instrument_type)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_watchlist_items_created_at ON watchlist_items(created_at DESC)")

    # -- user_portfolios --
    op.execute("""
        CREATE TABLE IF NOT EXISTS user_portfolios (
            user_portfolio_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id VARCHAR(255) NOT NULL
                REFERENCES users(user_id) ON DELETE CASCADE,
            symbol VARCHAR(50) NOT NULL,
            instrument_type VARCHAR(30) NOT NULL,
            exchange VARCHAR(50),
            name VARCHAR(255),
            quantity DECIMAL(18, 8) NOT NULL,
            average_cost DECIMAL(18, 4),
            currency VARCHAR(10) DEFAULT 'USD',
            account_name VARCHAR(100),
            notes TEXT,
            metadata JSONB DEFAULT '{}'::jsonb,
            first_purchased_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT unique_user_holding
                UNIQUE (user_id, symbol, instrument_type, account_name)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_portfolios_user_id ON user_portfolios(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_portfolios_symbol ON user_portfolios(symbol)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_portfolios_instrument_type ON user_portfolios(instrument_type)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_portfolios_user_instrument "
        "ON user_portfolios(user_id, symbol, instrument_type)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_portfolios_account ON user_portfolios(account_name)")

    # -- market_insights, with 007's VARCHAR user_id already applied --
    op.execute("""
        CREATE TABLE IF NOT EXISTS market_insights (
            market_insight_id UUID PRIMARY KEY,
            user_id VARCHAR(255),
            type VARCHAR(30) NOT NULL DEFAULT 'daily_brief',
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            headline TEXT,
            summary TEXT,
            content JSONB,
            topics JSONB,
            sources JSONB,
            model VARCHAR(10),
            error_message TEXT,
            generation_time_ms INTEGER,
            metadata JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            completed_at TIMESTAMPTZ
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_market_insights_latest
        ON market_insights (type, created_at DESC)
        WHERE status = 'completed' AND user_id IS NULL
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_market_insights_user
        ON market_insights (user_id, type, created_at DESC)
        WHERE status = 'completed' AND user_id IS NOT NULL
    """)
    # 005, folded in: one generating insight per user.
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_market_insights_user_generating
        ON market_insights (user_id)
        WHERE status = 'generating'
    """)

    # Same trigger 001 attaches to every table with an ``updated_at``.
    for table in ("watchlists", "watchlist_items", "user_portfolios"):
        trigger = f"trg_{table}_updated_at"
        op.execute(f"DROP TRIGGER IF EXISTS {trigger} ON {table}")
        op.execute(f"""
            CREATE TRIGGER {trigger}
                BEFORE UPDATE ON {table}
                FOR EACH ROW
                EXECUTE FUNCTION update_updated_at_column()
        """)


def downgrade() -> None:
    """Drop the restored schema, refusing while it still holds anything.

    Unlike the blob migration there is no reverse tool: neither table has a
    second home for its rows, so a downgrade that proceeded on live data would
    be an outright deletion. Locks are taken before the counts so a concurrent
    writer cannot land a row between the check and the DROP.
    """
    bind = op.get_bind()
    bind.execute(text("SET LOCAL lock_timeout = '5s'"))
    bind.execute(text(f"LOCK TABLE {', '.join(_TABLES)}, user_preferences IN ACCESS EXCLUSIVE MODE"))
    occupied = [
        (row[0], row[1])
        for row in bind.execute(text(_DATA_SQL)).fetchall()
        if row[1]
    ]
    if occupied:
        detail = ", ".join(f"{source}={rows}" for source, rows in occupied)
        raise RuntimeError(
            "the restored finance schema still holds data; export or delete it "
            f"before downgrading ({detail})"
        )

    for table in ("watchlist_items", "watchlists", "user_portfolios", "market_insights"):
        trigger = f"trg_{table}_updated_at"
        op.execute(f"DROP TRIGGER IF EXISTS {trigger} ON {table}")
    op.execute("DROP TABLE IF EXISTS watchlist_items")
    op.execute("DROP TABLE IF EXISTS watchlists")
    op.execute("DROP TABLE IF EXISTS user_portfolios")
    op.execute("DROP TABLE IF EXISTS market_insights")
    op.execute("""
        ALTER TABLE user_preferences
            DROP COLUMN IF EXISTS investment_preference,
            DROP COLUMN IF EXISTS risk_preference
    """)
