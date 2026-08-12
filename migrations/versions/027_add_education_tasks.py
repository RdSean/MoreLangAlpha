"""Add homework rules, instances, immutable submissions, and text reviews.

Revision ID: 027
Revises: 026
"""

from alembic import op


revision = "027"
down_revision = "026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE education_task_rules (
            task_rule_id UUID PRIMARY KEY,
            household_id UUID NOT NULL REFERENCES education_households(household_id) ON DELETE CASCADE,
            created_by_user_id VARCHAR(255) NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
            assigned_student_id VARCHAR(255) NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
            title VARCHAR(255) NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            recurrence JSONB NOT NULL,
            timezone VARCHAR(100) NOT NULL,
            status VARCHAR(16) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'stopped')),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            stopped_at TIMESTAMPTZ
        )
    """)
    op.execute("""
        CREATE TABLE education_tasks (
            task_id UUID PRIMARY KEY,
            task_rule_id UUID NOT NULL REFERENCES education_task_rules(task_rule_id) ON DELETE RESTRICT,
            household_id UUID NOT NULL REFERENCES education_households(household_id) ON DELETE CASCADE,
            assigned_student_id VARCHAR(255) NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
            occurrence_date DATE NOT NULL,
            due_at TIMESTAMPTZ NOT NULL,
            title VARCHAR(255) NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            status VARCHAR(24) NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'submitted', 'revision_requested', 'completed', 'cancelled')),
            cancelled_by_user_id VARCHAR(255) REFERENCES users(user_id) ON DELETE SET NULL,
            cancelled_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (task_rule_id, occurrence_date)
        )
    """)
    op.execute("""
        CREATE TABLE education_task_material_assets (
            task_id UUID NOT NULL REFERENCES education_tasks(task_id) ON DELETE CASCADE,
            asset_id UUID NOT NULL REFERENCES education_assets(asset_id) ON DELETE RESTRICT,
            PRIMARY KEY (task_id, asset_id)
        )
    """)
    op.execute("""
        CREATE TABLE education_task_submissions (
            submission_id UUID PRIMARY KEY,
            task_id UUID NOT NULL REFERENCES education_tasks(task_id) ON DELETE RESTRICT,
            submitted_by_user_id VARCHAR(255) NOT NULL REFERENCES users(user_id) ON DELETE RESTRICT,
            sequence INTEGER NOT NULL CHECK (sequence > 0),
            idempotency_key UUID,
            submission_text TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (task_id, sequence),
            UNIQUE (task_id, idempotency_key)
        )
    """)
    op.execute("""
        CREATE TABLE education_task_submission_assets (
            submission_id UUID NOT NULL REFERENCES education_task_submissions(submission_id) ON DELETE CASCADE,
            asset_id UUID NOT NULL REFERENCES education_assets(asset_id) ON DELETE RESTRICT,
            PRIMARY KEY (submission_id, asset_id)
        )
    """)
    op.execute("""
        CREATE TABLE education_task_reviews (
            review_id UUID PRIMARY KEY,
            submission_id UUID NOT NULL UNIQUE REFERENCES education_task_submissions(submission_id) ON DELETE RESTRICT,
            reviewed_by_user_id VARCHAR(255) NOT NULL REFERENCES users(user_id) ON DELETE RESTRICT,
            decision VARCHAR(24) NOT NULL CHECK (decision IN ('revision_requested', 'completed')),
            feedback_text TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX idx_education_task_rules_household_status ON education_task_rules (household_id, status)")
    op.execute("CREATE INDEX idx_education_tasks_assignee_due ON education_tasks (assigned_student_id, due_at DESC)")
    op.execute("CREATE INDEX idx_education_tasks_household_due ON education_tasks (household_id, due_at DESC)")
    op.execute("CREATE INDEX idx_education_task_submissions_task_sequence ON education_task_submissions (task_id, sequence DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE education_task_reviews")
    op.execute("DROP TABLE education_task_submission_assets")
    op.execute("DROP TABLE education_task_submissions")
    op.execute("DROP TABLE education_task_material_assets")
    op.execute("DROP TABLE education_tasks")
    op.execute("DROP TABLE education_task_rules")
