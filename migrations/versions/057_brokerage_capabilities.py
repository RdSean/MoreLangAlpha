"""Per-connection capability consent for brokerage connectors.

Ports the remaining half of remote ``036_brokerage_capabilities``: this chain
already carries ``sandbox_egress_grants.policy_required`` and its CHECK from
``055_tool_denylist``, so only the consent column is added here.

``granted_capabilities`` records what the user agreed a connection may do, as
group keys rather than tool names: intent outlives a vendor's tool list, and the
expansion from keys to names is done from source at grant-sync time, so a
curation change ships with a deploy and needs no data migration.

Revision ID: 057_brokerage_capabilities
Revises: 056_mcp_tool_binding
"""

from alembic import op


revision = "057_brokerage_capabilities"
down_revision = "056_mcp_tool_binding"
branch_labels = None
depends_on = None

# Pinned rather than imported: a migration records what the schema needed the
# day it ran, and BROKERAGES is free to grow afterwards. What each row gets is
# every group the vendor has EXCEPT the one that places real orders, which
# matches the consent dialog's own default. Nobody was asked about these
# connections, so what is written here is not consent and must not masquerade
# as it -- the page renders a stored key as a choice the user made.
_BACKFILL = """(VALUES
    ('robinhood', '["market_data","watchlists","scanners","account","order_preview"]'),
    ('ibkr',      '["market_data","watchlists","alerts","account","staged_orders"]'),
    ('moomoo',    '["market_data","watchlists","account","paper_trading"]')
) AS shipped(name, caps)"""


def upgrade() -> None:
    op.execute("""
        ALTER TABLE user_mcp_oauth_connections
          ADD COLUMN granted_capabilities JSONB
    """)

    # Nullable on purpose, and the three states are all meaningful: NULL is a
    # connection we curate no groups for (a user's own OAuth server), '[]' is a
    # brokerage granted nothing, and a populated array is a real choice.
    op.execute(f"""
        UPDATE user_mcp_oauth_connections c
           SET granted_capabilities = shipped.caps::jsonb
          FROM {_BACKFILL}
         WHERE c.server_name = shipped.name
           AND c.granted_capabilities IS NULL
    """)

    # Bumping the version is what makes the next resolve rewrite the grants
    # under the new consent, rather than an old grant persisting until something
    # unrelated invalidates the workspace.
    op.execute("""
        UPDATE workspaces ws SET mcp_config_version = ws.mcp_config_version + 1
         WHERE ws.user_id IN (
                   SELECT c.user_id
                     FROM user_mcp_oauth_connections c
                    WHERE c.granted_capabilities IS NOT NULL
               )
    """)


def downgrade() -> None:
    op.execute(
        "ALTER TABLE user_mcp_oauth_connections DROP COLUMN IF EXISTS granted_capabilities"
    )
