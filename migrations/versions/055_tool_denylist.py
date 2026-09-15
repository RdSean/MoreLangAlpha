"""Add the MCP egress tool denylist using an expand/contract migration.

The remote migration (038) assumes ``policy_required`` was introduced by its
brokerage-capability migration (036). This branch intentionally defers those
finance-only revisions, so this migration supplies that compatibility column
while preserving the local 046 allowlist contract during rolling deployment.
"""

from alembic import op


revision = "055_tool_denylist"
down_revision = "054_jsonb_deep_merge"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Expand, do not rename: old workers can keep reading tool_allowlist while
    # new workers write tool_denylist. policy_required normally comes from the
    # deferred remote 036 migration, so add it here as a prerequisite.
    op.execute("""
        ALTER TABLE sandbox_egress_grants
            ADD COLUMN IF NOT EXISTS tool_denylist JSONB,
            ADD COLUMN IF NOT EXISTS policy_required BOOLEAN NOT NULL DEFAULT false
    """)
    op.execute("""
        ALTER TABLE sandbox_egress_grants
            DROP CONSTRAINT IF EXISTS sandbox_egress_grants_policy_present
    """)

    # A policy written against the old allowlist was not a computed denylist.
    # Clear the marker before installing the rolling-deploy constraint.
    op.execute("""
        UPDATE sandbox_egress_grants
           SET policy_required = false, updated_at = NOW()
         WHERE policy_required
    """)
    op.execute("""
        ALTER TABLE sandbox_egress_grants
            ADD CONSTRAINT sandbox_egress_grants_policy_present
            CHECK (NOT (policy_required
                        AND tool_denylist IS NULL
                        AND tool_allowlist IS NULL))
    """)

    # Do not derive a denial from an old allowlist: that needs the historical
    # curation map. Force each OAuth workspace to resolve a fresh policy.
    op.execute("""
        UPDATE workspaces ws
           SET mcp_config_version = ws.mcp_config_version + 1
         WHERE ws.user_id IN (
             SELECT DISTINCT user_id FROM user_mcp_oauth_connections
         )
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE sandbox_egress_grants
            DROP CONSTRAINT IF EXISTS sandbox_egress_grants_policy_present
    """)

    # Pre-055 code treats NULL allowlist as unrestricted. Convert every policy
    # written in the new vocabulary to [] before destroying the denylist so a
    # rollback refuses all curated tools until the old resolver recomputes.
    op.execute("""
        UPDATE sandbox_egress_grants
           SET tool_allowlist = '[]'::jsonb,
               policy_required = true,
               updated_at = NOW()
         WHERE tool_denylist IS NOT NULL
    """)
    op.execute("""
        ALTER TABLE sandbox_egress_grants
            DROP COLUMN IF EXISTS tool_denylist
    """)

    # This branch did not port remote 036, so 055 owns policy_required and must
    # remove it to return to the exact 054 schema. The fail-closed allowlist
    # written above remains after this compatibility column is removed.
    op.execute(
        "ALTER TABLE sandbox_egress_grants "
        "DROP COLUMN IF EXISTS policy_required"
    )
    op.execute("""
        UPDATE workspaces ws
           SET mcp_config_version = ws.mcp_config_version + 1
         WHERE ws.user_id IN (
             SELECT DISTINCT user_id FROM user_mcp_oauth_connections
         )
    """)
