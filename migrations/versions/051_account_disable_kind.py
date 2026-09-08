"""Allow account-wide disables to target builtin servers or bundles.

Semantic port of origin/main revision ``031_account_disable_kind``. The remote
chain passed through finance-only revisions 030, but this table change has no
foreign-key or data dependency on brokerage features, so it is safe to append
directly after the local plugin-secret migration.
"""

from alembic import op


revision = "051_account_disable_kind"
down_revision = "050_plugin_owned_secrets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE user_mcp_builtin_disables
            ADD COLUMN IF NOT EXISTS kind VARCHAR(16) NOT NULL DEFAULT 'server'
    """)
    op.execute("""
        ALTER TABLE user_mcp_builtin_disables
            DROP CONSTRAINT IF EXISTS user_mcp_builtin_disables_kind_check
    """)
    op.execute("""
        ALTER TABLE user_mcp_builtin_disables
            ADD CONSTRAINT user_mcp_builtin_disables_kind_check
            CHECK (kind IN ('server', 'bundle'))
    """)
    op.execute("""
        ALTER TABLE user_mcp_builtin_disables
            DROP CONSTRAINT IF EXISTS user_mcp_builtin_disables_pkey
    """)
    op.execute("""
        ALTER TABLE user_mcp_builtin_disables
            ADD PRIMARY KEY (user_id, kind, name)
    """)
    op.execute("""
        ALTER TABLE user_mcp_builtin_disables ALTER COLUMN kind DROP DEFAULT
    """)
    op.execute("""
        COMMENT ON TABLE user_mcp_builtin_disables IS
        'Account-wide off switches for shipped things. A row is a disable; '
        'absence is enabled. kind distinguishes builtin MCP servers from '
        'plugins/bundles.'
    """)


def downgrade() -> None:
    op.execute("DELETE FROM user_mcp_builtin_disables WHERE kind <> 'server'")
    op.execute("""
        ALTER TABLE user_mcp_builtin_disables
            DROP CONSTRAINT IF EXISTS user_mcp_builtin_disables_pkey
    """)
    op.execute("ALTER TABLE user_mcp_builtin_disables DROP COLUMN IF EXISTS kind")
    op.execute("""
        ALTER TABLE user_mcp_builtin_disables
            ADD PRIMARY KEY (user_id, name)
    """)
    op.execute("COMMENT ON TABLE user_mcp_builtin_disables IS NULL")
