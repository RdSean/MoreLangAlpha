"""Retain service-owned runtime identities across interrupted preparation."""

from migrations.textbook_ddl import execute_textbook_ddl as execute

revision = "085_book_attempt_runtime_identity"
down_revision = "084_textbook_preparation_timing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute("""
      ALTER TABLE education_book_job_attempts
        ADD COLUMN managed_workspace_id UUID REFERENCES workspaces(workspace_id) ON DELETE RESTRICT,
        ADD COLUMN managed_thread_id UUID REFERENCES conversation_threads(conversation_thread_id) ON DELETE RESTRICT;
      UPDATE education_book_job_attempts a SET managed_workspace_id=i.managed_workspace_id,
        managed_thread_id=i.managed_thread_id FROM education_book_job_items i
        WHERE a.item_id=i.item_id AND a.attempt_token=i.attempt_token;
      CREATE FUNCTION education_book_attempt_runtime_identity() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN
        IF NEW.status='running' THEN
          UPDATE education_book_job_attempts SET managed_workspace_id=NEW.managed_workspace_id,
            managed_thread_id=NEW.managed_thread_id
            WHERE item_id=NEW.item_id AND attempt_token=NEW.attempt_token;
        END IF;
        RETURN NEW;
      END $$;
      CREATE TRIGGER book_runtime_identity AFTER UPDATE ON education_book_job_items
        FOR EACH ROW EXECUTE FUNCTION education_book_attempt_runtime_identity();
    """)


def downgrade() -> None:
    execute("""
      LOCK TABLE education_book_job_attempts IN ACCESS EXCLUSIVE MODE;
      DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM education_book_job_attempts a JOIN workspaces w
          ON w.workspace_id=a.managed_workspace_id WHERE w.status<>'deleted') THEN
          RAISE EXCEPTION '085 rollback requires settled runtime cleanup';
        END IF;
      END $$;
      DROP TRIGGER book_runtime_identity ON education_book_job_items;
      DROP FUNCTION education_book_attempt_runtime_identity();
      ALTER TABLE education_book_job_attempts DROP COLUMN managed_workspace_id,DROP COLUMN managed_thread_id;
    """)
