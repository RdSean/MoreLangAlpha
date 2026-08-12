"""Add first-party local authentication and household memberships.

Revision ID: 025
Revises: 024
"""

from alembic import op


revision = "025"
down_revision = "024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE local_auth_accounts (
            user_id VARCHAR(255) PRIMARY KEY
                REFERENCES users(user_id) ON DELETE CASCADE,
            login_identifier VARCHAR(255) NOT NULL UNIQUE,
            email VARCHAR(255),
            password_hash TEXT NOT NULL,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE TABLE local_auth_sessions (
            session_id UUID PRIMARY KEY,
            user_id VARCHAR(255) NOT NULL
                REFERENCES users(user_id) ON DELETE CASCADE,
            token_digest CHAR(64) NOT NULL UNIQUE,
            expires_at TIMESTAMPTZ NOT NULL,
            revoked_at TIMESTAMPTZ,
            replaced_by_session_id UUID
                REFERENCES local_auth_sessions(session_id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX idx_local_auth_sessions_user_active
        ON local_auth_sessions (user_id, expires_at DESC)
        WHERE revoked_at IS NULL
    """)
    op.execute("""
        CREATE TABLE education_households (
            household_id UUID PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            timezone VARCHAR(100) NOT NULL DEFAULT 'UTC',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE TABLE education_memberships (
            household_id UUID NOT NULL
                REFERENCES education_households(household_id) ON DELETE CASCADE,
            user_id VARCHAR(255) NOT NULL
                REFERENCES users(user_id) ON DELETE CASCADE,
            role VARCHAR(16) NOT NULL CHECK (role IN ('parent', 'student')),
            display_name VARCHAR(255) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (household_id, user_id)
        )
    """)
    op.execute("""
        CREATE INDEX idx_education_memberships_user
        ON education_memberships (user_id, created_at ASC)
    """)
    op.execute("""
        CREATE INDEX idx_education_memberships_household_role
        ON education_memberships (household_id, role, created_at ASC)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE education_memberships")
    op.execute("DROP TABLE education_households")
    op.execute("DROP TABLE local_auth_sessions")
    op.execute("DROP TABLE local_auth_accounts")
