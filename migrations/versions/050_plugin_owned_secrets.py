"""Record which installed plugin introduced a user Vault secret."""

from alembic import op


revision = "050_plugin_owned_secrets"
down_revision = "049_agent_plugins"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET lock_timeout = '5s'")
    op.execute("""
        ALTER TABLE user_vault_secrets
        ADD COLUMN IF NOT EXISTS plugin_id UUID NULL
    """)
    op.execute("""
        ALTER TABLE user_vault_secrets
        DROP CONSTRAINT IF EXISTS fk_user_vault_secrets_plugin
    """)
    op.execute("""
        ALTER TABLE user_vault_secrets
        ADD CONSTRAINT fk_user_vault_secrets_plugin
        FOREIGN KEY (user_id, plugin_id)
        REFERENCES user_plugins(user_id, user_plugin_id)
        ON DELETE SET NULL (plugin_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_user_vault_secrets_plugin
        ON user_vault_secrets(plugin_id)
        WHERE plugin_id IS NOT NULL
    """)


def downgrade() -> None:
    op.execute(
        "ALTER TABLE user_vault_secrets "
        "DROP CONSTRAINT IF EXISTS fk_user_vault_secrets_plugin"
    )
    op.execute("DROP INDEX IF EXISTS idx_user_vault_secrets_plugin")
    op.execute("ALTER TABLE user_vault_secrets DROP COLUMN IF EXISTS plugin_id")
