"""Add user-level MCP state, OAuth storage, tool schemas and egress grants.

This is the semantic port of origin/main's ``025_mcp_connectors`` migration.
The local branch already uses revision IDs 025--045 for education, household,
channel and document-library features, so this migration intentionally starts
at the local head instead of reusing the remote revision ID.
"""

from alembic import op


revision = "046_mcp_platform_core"
down_revision = "045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF current_setting('server_version_num')::int < 150000 THEN
                RAISE EXCEPTION
                    'migration 046 requires PostgreSQL 15+ (UNIQUE NULLS NOT '
                    'DISTINCT); server is %', current_setting('server_version');
            END IF;
        END $$;
    """)

    # Existing rows are templates until explicitly enabled by the user.
    op.execute("""
        ALTER TABLE user_mcp_servers
        ADD COLUMN IF NOT EXISTS enabled BOOLEAN NOT NULL DEFAULT FALSE
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS user_vault_secrets (
            user_vault_secret_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id VARCHAR(255) NOT NULL,
            name VARCHAR(255) NOT NULL,
            value BYTEA NOT NULL,
            description TEXT DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(user_id, name)
        )
    """)
    op.execute("DROP TRIGGER IF EXISTS update_user_vault_secrets_updated_at ON user_vault_secrets")
    op.execute("""
        CREATE TRIGGER update_user_vault_secrets_updated_at
        BEFORE UPDATE ON user_vault_secrets
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS user_mcp_oauth_connections (
            connection_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id VARCHAR(255) NOT NULL,
            server_name VARCHAR(255) NOT NULL,
            server_url TEXT NOT NULL,
            access_token BYTEA NULL,
            refresh_token BYTEA NULL,
            token_type VARCHAR(32) NOT NULL DEFAULT 'Bearer',
            scope TEXT NULL,
            expires_at TIMESTAMPTZ NULL,
            token_generation INTEGER NOT NULL DEFAULT 0,
            client_info JSONB NULL,
            client_secret BYTEA NULL,
            as_metadata JSONB NULL,
            resource_metadata JSONB NULL,
            status VARCHAR(32) NOT NULL DEFAULT 'connected',
            last_refresh_at TIMESTAMPTZ NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(user_id, server_name)
        )
    """)
    op.execute("DROP TRIGGER IF EXISTS update_user_mcp_oauth_connections_updated_at ON user_mcp_oauth_connections")
    op.execute("""
        CREATE TRIGGER update_user_mcp_oauth_connections_updated_at
        BEFORE UPDATE ON user_mcp_oauth_connections
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_mcp_oauth_connections_due
        ON user_mcp_oauth_connections(expires_at)
        WHERE status = 'connected'
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS user_mcp_tool_schemas (
            user_id VARCHAR(255) NOT NULL,
            server_name VARCHAR(255) NOT NULL,
            config_hash TEXT NOT NULL,
            tools JSONB NOT NULL DEFAULT '[]',
            status VARCHAR(16) NOT NULL DEFAULT 'pending',
            error TEXT NOT NULL DEFAULT '',
            schema_digest TEXT NOT NULL DEFAULT '',
            observed_meta JSONB NOT NULL DEFAULT '{}',
            discovered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(user_id, server_name, config_hash)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_user_mcp_tool_schemas_lookup
        ON user_mcp_tool_schemas(user_id, server_name, discovered_at DESC)
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS sandbox_egress_grants (
            grant_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id VARCHAR(255) NOT NULL,
            workspace_id UUID NOT NULL REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
            kind VARCHAR(32) NOT NULL,
            connection_id UUID NULL REFERENCES user_mcp_oauth_connections(connection_id) ON DELETE CASCADE,
            resolver_config JSONB NOT NULL DEFAULT '{}',
            destination_url TEXT NOT NULL,
            allowed_methods JSONB NOT NULL DEFAULT '["POST"]',
            tool_allowlist JSONB NULL,
            policy_version INTEGER NOT NULL DEFAULT 1,
            status VARCHAR(16) NOT NULL DEFAULT 'active',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE NULLS NOT DISTINCT (workspace_id, kind, connection_id)
        )
    """)
    op.execute("DROP TRIGGER IF EXISTS update_sandbox_egress_grants_updated_at ON sandbox_egress_grants")
    op.execute("""
        CREATE TRIGGER update_sandbox_egress_grants_updated_at
        BEFORE UPDATE ON sandbox_egress_grants
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_sandbox_egress_grants_connection
        ON sandbox_egress_grants(connection_id)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS sandbox_egress_grants CASCADE")
    op.execute("DROP TABLE IF EXISTS user_mcp_tool_schemas CASCADE")
    op.execute("DROP TABLE IF EXISTS user_mcp_oauth_connections CASCADE")
    op.execute("DROP TABLE IF EXISTS user_vault_secrets CASCADE")
    op.execute("ALTER TABLE user_mcp_servers DROP COLUMN IF EXISTS enabled")
