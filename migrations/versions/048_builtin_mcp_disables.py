"""Add account-wide builtin MCP disable markers.

Semantic port of origin/main revision ``027_user_mcp_builtin_disables``.
"""

from alembic import op


revision = "048_builtin_mcp_disables"
down_revision = "047_user_skills"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS user_mcp_builtin_disables (
            user_id VARCHAR(255) NOT NULL,
            name VARCHAR(255) NOT NULL,
            disabled_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (user_id, name)
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS user_mcp_builtin_disables")
