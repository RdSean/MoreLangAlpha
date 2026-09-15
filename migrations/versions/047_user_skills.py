"""Add user/workspace skill rows, archives and inherited-skill disables.

Semantic port of origin/main revision ``026_user_skills``. The local branch
uses revision ``047_user_skills`` because local revisions through 045 are
product-specific and 046 is the MCP platform base.
"""

from alembic import op


revision = "047_user_skills"
down_revision = "046_mcp_platform_core"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS user_skills (
            user_skill_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id VARCHAR(255) NOT NULL,
            workspace_id UUID NULL,
            name VARCHAR(64) NOT NULL,
            command VARCHAR(64) NULL,
            description TEXT NOT NULL DEFAULT '',
            license TEXT NULL,
            frontmatter JSONB NOT NULL DEFAULT '{}',
            allowed_tools JSONB NOT NULL DEFAULT '[]',
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            confirmed BOOLEAN NOT NULL DEFAULT TRUE,
            plugin_id UUID NULL,
            plugin_skill_dir TEXT NULL,
            content_hash VARCHAR(71) NOT NULL,
            archive_key TEXT NULL,
            archive_blob BYTEA NULL,
            archive_bytes BIGINT NOT NULL DEFAULT 0,
            file_count INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT user_skills_archive_present CHECK (
                (archive_key IS NULL) <> (archive_blob IS NULL)
            )
        )
    """)
    op.execute("DROP TRIGGER IF EXISTS update_user_skills_updated_at ON user_skills")
    op.execute("""
        CREATE TRIGGER update_user_skills_updated_at
        BEFORE UPDATE ON user_skills
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()
    """)

    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_user_skills_user_name
        ON user_skills(user_id, name)
        WHERE workspace_id IS NULL
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_user_skills_workspace_name
        ON user_skills(workspace_id, name)
        WHERE workspace_id IS NOT NULL
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_user_skills_user_command
        ON user_skills(user_id, command)
        WHERE workspace_id IS NULL AND command IS NOT NULL
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_user_skills_workspace_command
        ON user_skills(workspace_id, command)
        WHERE workspace_id IS NOT NULL AND command IS NOT NULL
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_user_skills_user
        ON user_skills(user_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_user_skills_archive_key
        ON user_skills(archive_key)
        WHERE archive_key IS NOT NULL
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_user_skills_workspace
        ON user_skills(workspace_id)
        WHERE workspace_id IS NOT NULL
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_user_skills_plugin
        ON user_skills(plugin_id)
        WHERE plugin_id IS NOT NULL
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS workspace_skill_disables (
            workspace_id UUID NOT NULL,
            name VARCHAR(64) NOT NULL,
            disabled_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (workspace_id, name)
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS workspace_skill_disables CASCADE")
    op.execute("DROP TABLE IF EXISTS user_skills CASCADE")
