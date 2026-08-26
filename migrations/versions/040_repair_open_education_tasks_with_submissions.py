"""Repair legacy open homework tasks that already have submissions.

Revision ID: 040
Revises: 039
"""

from alembic import op


revision = "040"
down_revision = "039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Before the strict 039 state cutover, the compatibility trigger recorded
    # completion time but old service writes could leave the task itself open.
    # Keep the first student submission as the completion fact.
    op.execute(
        """
        UPDATE education_tasks AS tasks
        SET status = 'completed',
            completed_at = COALESCE(
                tasks.completed_at,
                (
                    SELECT MIN(submissions.created_at)
                    FROM education_task_submissions AS submissions
                    WHERE submissions.task_id = tasks.task_id
                )
            )
        WHERE tasks.status = 'open'
          AND EXISTS (
              SELECT 1
              FROM education_task_submissions AS submissions
              WHERE submissions.task_id = tasks.task_id
          )
        """
    )


def downgrade() -> None:
    # The prior open state cannot be distinguished from an intentionally
    # completed task after the repair, so this forward data correction is kept.
    return None
