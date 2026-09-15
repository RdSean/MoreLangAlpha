"""Add user-installed plugin identity and component ownership.

Semantic port of origin/main revision ``028_agent_plugins``. Plugin-owned
components use RESTRICT foreign keys so uninstall must run the existing purge
helpers rather than relying on a database cascade.
"""

from alembic import op


revision = "049_agent_plugins"
down_revision = "048_builtin_mcp_disables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET lock_timeout = '5s'")

    op.execute("""
        CREATE TABLE IF NOT EXISTS user_plugins (
            user_plugin_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id VARCHAR(255) NOT NULL,
            name VARCHAR(64) NOT NULL,
            version TEXT NULL,
            source_type VARCHAR(8) NOT NULL,
            source_ref TEXT NULL,
            manifest JSONB NOT NULL,
            mcp_document JSONB NULL,
            content_hash TEXT NOT NULL,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            installed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (user_id, name)
        )
    """)
    op.execute("DROP TRIGGER IF EXISTS update_user_plugins_updated_at ON user_plugins")
    op.execute("""
        CREATE TRIGGER update_user_plugins_updated_at
        BEFORE UPDATE ON user_plugins
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()
    """)
    op.execute("ALTER TABLE user_plugins DROP CONSTRAINT IF EXISTS uq_user_plugins_owner")
    op.execute("""
        ALTER TABLE user_plugins
        ADD CONSTRAINT uq_user_plugins_owner UNIQUE (user_id, user_plugin_id)
    """)

    op.execute("""
        ALTER TABLE user_mcp_servers
        ADD COLUMN IF NOT EXISTS plugin_id UUID NULL,
        ADD COLUMN IF NOT EXISTS plugin_server_key TEXT NULL
    """)
    op.execute("ALTER TABLE user_mcp_servers DROP CONSTRAINT IF EXISTS fk_user_mcp_servers_plugin")
    op.execute("""
        ALTER TABLE user_mcp_servers
        ADD CONSTRAINT fk_user_mcp_servers_plugin
        FOREIGN KEY (user_id, plugin_id)
        REFERENCES user_plugins(user_id, user_plugin_id)
        ON DELETE RESTRICT
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_user_mcp_servers_plugin
        ON user_mcp_servers(plugin_id)
        WHERE plugin_id IS NOT NULL
    """)

    op.execute("ALTER TABLE user_skills DROP CONSTRAINT IF EXISTS fk_user_skills_plugin")
    op.execute("""
        ALTER TABLE user_skills
        ADD CONSTRAINT fk_user_skills_plugin
        FOREIGN KEY (user_id, plugin_id)
        REFERENCES user_plugins(user_id, user_plugin_id)
        ON DELETE RESTRICT
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE user_skills DROP CONSTRAINT IF EXISTS fk_user_skills_plugin")
    op.execute("ALTER TABLE user_mcp_servers DROP CONSTRAINT IF EXISTS fk_user_mcp_servers_plugin")
    op.execute("DROP INDEX IF EXISTS idx_user_mcp_servers_plugin")
    # Preserve disabled plugin delivery semantics before dropping plugin_id.
    op.execute("""
        UPDATE user_mcp_servers s SET enabled = FALSE
        FROM user_plugins p
        WHERE s.plugin_id = p.user_plugin_id AND p.enabled = FALSE
    """)
    op.execute("""
        UPDATE user_skills k SET enabled = FALSE
        FROM user_plugins p
        WHERE k.plugin_id = p.user_plugin_id AND p.enabled = FALSE
    """)
    op.execute("ALTER TABLE user_mcp_servers DROP COLUMN IF EXISTS plugin_id, DROP COLUMN IF EXISTS plugin_server_key")
    op.execute("UPDATE user_skills SET plugin_id = NULL, plugin_skill_dir = NULL WHERE plugin_id IS NOT NULL")
    op.execute("DROP TABLE IF EXISTS user_plugins CASCADE")
