"""Record authoritative queue and terminal timing boundaries transactionally."""

from migrations.textbook_ddl import execute_textbook_ddl as execute

revision = "086_book_timing_boundaries"
down_revision = "085_book_attempt_runtime_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute("""
      CREATE FUNCTION education_book_timing_boundaries() RETURNS trigger LANGUAGE plpgsql AS $$
      DECLARE finish TIMESTAMPTZ; elapsed BIGINT;
      BEGIN
        IF NEW.status='running' AND NEW.attempt_token IS DISTINCT FROM OLD.attempt_token
          AND NEW.queued_at IS NOT NULL AND NOW()>=NEW.queued_at THEN
          INSERT INTO education_book_job_phase_spans
            (segment_id,attempt_id,phase,started_at,ended_at,status,measured_ms)
          VALUES (gen_random_uuid(),NEW.attempt_token,
            CASE WHEN NEW.execution_phase='source_freezing' THEN 'initial_queue' ELSE 'runtime_queue' END,
            NEW.queued_at,NOW(),'succeeded',ROUND(EXTRACT(EPOCH FROM (NOW()-NEW.queued_at))*1000)::bigint);
        END IF;
        IF NEW.status='running' AND OLD.status='running' AND NEW.attempt_token=OLD.attempt_token
          AND NEW.execution_phase IS DISTINCT FROM OLD.execution_phase THEN
          IF OLD.execution_phase='runtime_queue' THEN
            UPDATE education_book_job_phase_spans SET ended_at=GREATEST(started_at,NOW()),status='succeeded',
              measured_ms=CASE WHEN NOW()>=started_at THEN ROUND(EXTRACT(EPOCH FROM (NOW()-started_at))*1000)::bigint END
              WHERE attempt_id=NEW.attempt_token AND phase='runtime_queue' AND status='running';
          END IF;
          IF NEW.execution_phase='runtime_queue' THEN
            UPDATE education_book_job_phase_spans SET ended_at=GREATEST(started_at,NOW()),status='succeeded'
              WHERE attempt_id=NEW.attempt_token AND phase='source_freezing' AND status='running';
            INSERT INTO education_book_job_phase_spans (segment_id,attempt_id,phase,started_at,status)
              VALUES (gen_random_uuid(),NEW.attempt_token,'runtime_queue',NOW(),'running');
          END IF;
        END IF;
        IF OLD.status='running' AND (NEW.status<>'running' OR NEW.attempt_token IS DISTINCT FROM OLD.attempt_token) THEN
          finish:=COALESCE(NEW.finished_at,NOW());
          elapsed:=CASE WHEN OLD.queued_at IS NOT NULL AND finish>=OLD.queued_at
            THEN ROUND(EXTRACT(EPOCH FROM (finish-OLD.queued_at))*1000)::bigint END;
          UPDATE education_book_job_attempts SET total_ms=elapsed WHERE attempt_token=OLD.attempt_token;
          -- The attempt ledger closes open segments first in this transaction.
          UPDATE education_book_job_phase_spans SET
            status=CASE WHEN NEW.status IN ('succeeded','failed','cancelled') THEN NEW.status ELSE 'interrupted' END,
            measured_ms=CASE WHEN phase IN ('initial_queue','runtime_queue') AND finish>=started_at
              THEN ROUND(EXTRACT(EPOCH FROM (finish-started_at))*1000)::bigint ELSE measured_ms END
            WHERE attempt_id=OLD.attempt_token AND status='interrupted' AND ended_at=GREATEST(started_at,NOW());
        END IF;
        RETURN NEW;
      END $$;
      CREATE TRIGGER book_timing_windows AFTER UPDATE ON education_book_job_items
        FOR EACH ROW EXECUTE FUNCTION education_book_timing_boundaries();
    """)


def downgrade() -> None:
    execute("""
      DROP TRIGGER book_timing_windows ON education_book_job_items;
      DROP FUNCTION education_book_timing_boundaries();
    """)
