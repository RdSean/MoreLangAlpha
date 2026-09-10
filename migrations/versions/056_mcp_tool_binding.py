"""Per-row tool binding settings: overrides, a preset, and the approval switch.

Ports remote ``041_tool_binding`` onto the local chain. Which path a tool takes
to the model used to be a property of its capability group alone. These three
columns let the user say otherwise for one row: ``tool_binding`` is the
per-tool map (``ptc`` | ``direct`` | ``both``), ``binding_preset`` the row-level
shortcut the Plugins page offers, and ``order_approval`` whether live orders
through this row stop for the user's confirmation on every call. The defaults
reproduce exactly what every row did before, so no backfill is needed.

Revision ID: 056_mcp_tool_binding
Revises: 055_tool_denylist
"""

from alembic import op


revision = "056_mcp_tool_binding"
down_revision = "055_tool_denylist"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE user_mcp_servers
          ADD COLUMN tool_binding JSONB NOT NULL DEFAULT '{}'::jsonb,
          ADD COLUMN binding_preset VARCHAR(32),
          ADD COLUMN order_approval BOOLEAN NOT NULL DEFAULT TRUE
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE user_mcp_servers
          DROP COLUMN IF EXISTS tool_binding,
          DROP COLUMN IF EXISTS binding_preset,
          DROP COLUMN IF EXISTS order_approval
    """)
