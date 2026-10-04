"""Persist pinned source preparation and reliable per-attempt timing."""

from migrations.textbook_ddl import execute_textbook_ddl as execute

revision = "084_textbook_preparation_timing"
down_revision = "083_textbook_deletion_cleanup"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute("""
        ALTER TABLE education_textbooks
          ADD COLUMN source_status TEXT NOT NULL DEFAULT 'ready'
            CHECK (source_status IN ('pending','preparing','ready','failed','cancelled')),
          ADD COLUMN source_frozen_at TIMESTAMPTZ,
          ADD COLUMN selected_source JSONB,
          ADD COLUMN preparation_descriptor JSONB,
          ALTER COLUMN source_content_sha256 DROP NOT NULL,
          ALTER COLUMN source_size_bytes DROP NOT NULL,
          ALTER COLUMN source_snapshot_prefix DROP NOT NULL,
          ALTER COLUMN source_markdown_key DROP NOT NULL;
        ALTER TABLE education_textbooks
          DROP CONSTRAINT education_textbooks_check;
        ALTER TABLE education_textbooks ADD CONSTRAINT book_source_prefix_shape CHECK (
          source_snapshot_prefix IS NULL OR
          source_snapshot_prefix = 'education/' || household_id::text || '/textbooks/' || textbook_id::text || '/source/' OR
          source_snapshot_prefix ~ ('^education/' || household_id::text || '/textbooks/' || textbook_id::text ||
            '/source/attempts/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/$')
        );
        ALTER TABLE education_textbooks ADD CONSTRAINT book_source_ready_complete CHECK (
          (source_status = 'ready' AND source_content_sha256 IS NOT NULL AND source_size_bytes IS NOT NULL
            AND source_snapshot_prefix IS NOT NULL AND source_markdown_key IS NOT NULL
            AND length(source_markdown_key) > length(source_snapshot_prefix)) OR
          (source_status <> 'ready' AND source_content_sha256 IS NULL AND source_size_bytes IS NULL
            AND source_snapshot_prefix IS NULL AND source_markdown_key IS NULL
            AND source_blocks_key IS NULL AND source_report_key IS NULL AND source_frozen_at IS NULL
            AND selected_source IS NOT NULL AND preparation_descriptor IS NOT NULL)
        );
        ALTER TABLE education_book_jobs
          ADD COLUMN request_round INTEGER NOT NULL DEFAULT 1 CHECK (request_round > 0),
          ADD COLUMN round_accepted_at TIMESTAMPTZ,
          ADD COLUMN previous_job_id UUID REFERENCES education_book_jobs(job_id) ON DELETE SET NULL;
        ALTER TABLE education_book_jobs ALTER COLUMN round_accepted_at SET DEFAULT NOW();
        ALTER TABLE education_book_job_items
          ADD COLUMN queued_at TIMESTAMPTZ,
          ADD COLUMN execution_phase TEXT CHECK (execution_phase IN (
            'initial_queue','source_freezing','runtime_queue','sandbox_preparation',
            'input_staging','ptc_execution','finalization'));
        ALTER TABLE education_book_job_items ALTER COLUMN queued_at SET DEFAULT NOW();
        ALTER TABLE education_book_job_items ALTER COLUMN execution_phase SET DEFAULT 'initial_queue';
        CREATE TABLE education_book_creation_requests (
          household_id UUID NOT NULL REFERENCES education_households(household_id) ON DELETE CASCADE,
          idempotency_key VARCHAR(160) NOT NULL,
          request_payload JSONB NOT NULL,
          textbook_id UUID NOT NULL REFERENCES education_textbooks(textbook_id) ON DELETE CASCADE,
          job_id UUID NOT NULL REFERENCES education_book_jobs(job_id) ON DELETE CASCADE,
          PRIMARY KEY (household_id,idempotency_key)
        );
        CREATE TABLE education_book_job_attempts (
          attempt_id UUID PRIMARY KEY,
          item_id UUID NOT NULL REFERENCES education_book_job_items(item_id) ON DELETE CASCADE,
          attempt INTEGER NOT NULL CHECK (attempt > 0),
          request_round INTEGER NOT NULL CHECK (request_round > 0),
          attempt_token UUID NOT NULL UNIQUE,
          execution_id UUID,
          run_id UUID,
          status TEXT NOT NULL CHECK (status IN ('running','succeeded','failed','cancelled','interrupted')),
          execution_phase TEXT,
          queued_at TIMESTAMPTZ,
          claimed_at TIMESTAMPTZ,
          terminal_at TIMESTAMPTZ,
          timing_status TEXT NOT NULL DEFAULT 'unavailable' CHECK (timing_status IN ('available','partial','unavailable')),
          total_ms BIGINT CHECK (total_ms >= 0),
          total_resources INTEGER CHECK (total_resources >= 0),
          verified_resources INTEGER NOT NULL DEFAULT 0 CHECK (verified_resources >= 0),
          source_identity JSONB NOT NULL,
          candidate_objects JSONB NOT NULL DEFAULT '[]'::jsonb,
          UNIQUE (item_id,attempt),
          CHECK (total_resources IS NULL OR verified_resources <= total_resources)
        );
        CREATE TABLE education_book_job_phase_spans (
          segment_id UUID PRIMARY KEY,
          attempt_id UUID NOT NULL REFERENCES education_book_job_attempts(attempt_id) ON DELETE CASCADE,
          phase TEXT NOT NULL CHECK (phase IN ('initial_queue','source_freezing','runtime_queue',
            'sandbox_preparation','input_staging','ptc_execution','finalization')),
          started_at TIMESTAMPTZ NOT NULL,
          ended_at TIMESTAMPTZ,
          status TEXT NOT NULL CHECK (status IN ('running','succeeded','failed','cancelled','interrupted')),
          measured_ms BIGINT CHECK (measured_ms >= 0),
          CHECK (ended_at IS NULL OR ended_at >= started_at),
          CHECK (measured_ms IS NULL OR ended_at IS NOT NULL)
        );
        CREATE INDEX book_attempt_history ON education_book_job_attempts(item_id,attempt DESC);
        CREATE INDEX book_phase_attempt ON education_book_job_phase_spans(attempt_id,started_at,segment_id);
    """)
    # Track terminal facts in the same transaction as every existing finalizer.
    execute("""
      CREATE FUNCTION education_book_attempt_ledger() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN
        IF NEW.attempt_token IS NOT NULL AND NEW.attempt > 0 AND NEW.status = 'running' THEN
          INSERT INTO education_book_job_attempts (
            attempt_id,item_id,attempt,request_round,attempt_token,execution_id,run_id,
            status,execution_phase,queued_at,claimed_at,source_identity,candidate_objects
          ) SELECT NEW.attempt_token,NEW.item_id,NEW.attempt,j.request_round,NEW.attempt_token,
            NEW.execution_id,NEW.run_id,'running',NEW.execution_phase,NEW.queued_at,NEW.started_at,
            jsonb_build_object('document_id',b.source_document_id,'parse_job_id',b.source_parse_job_id,
              'primary_artifact_id',b.source_primary_artifact_id), NEW.candidate_objects
          FROM education_book_jobs j JOIN education_textbooks b ON b.textbook_id=j.textbook_id
          WHERE j.job_id=NEW.job_id
          ON CONFLICT (item_id,attempt) DO UPDATE SET
            run_id=EXCLUDED.run_id,execution_phase=EXCLUDED.execution_phase,candidate_objects=EXCLUDED.candidate_objects;
        END IF;
        IF OLD.status = 'running' AND (NEW.status <> 'running' OR NEW.attempt_token IS DISTINCT FROM OLD.attempt_token) THEN
          UPDATE education_book_job_attempts SET
            status=CASE WHEN NEW.status IN ('succeeded','failed','cancelled') THEN NEW.status ELSE 'interrupted' END,
            terminal_at=COALESCE(NEW.finished_at,NOW())
          WHERE item_id=OLD.item_id AND attempt_token=OLD.attempt_token AND status='running';
          UPDATE education_book_job_phase_spans SET status='interrupted',ended_at=GREATEST(started_at,NOW())
          WHERE attempt_id=OLD.attempt_token AND status='running';
          IF NEW.kind='structure' AND NEW.status IN ('failed','cancelled') THEN
            UPDATE education_textbooks SET source_status=NEW.status,updated_at=NOW()
              WHERE textbook_id=(SELECT textbook_id FROM education_book_jobs WHERE job_id=NEW.job_id)
                AND source_status<>'ready';
          END IF;
        END IF;
        RETURN NEW;
      END $$;
      CREATE TRIGGER book_attempt_ledger AFTER UPDATE ON education_book_job_items
        FOR EACH ROW EXECUTE FUNCTION education_book_attempt_ledger();
    """)


def downgrade() -> None:
    execute("""
      LOCK TABLE education_textbooks,education_book_jobs,education_book_job_items IN ACCESS EXCLUSIVE MODE;
      DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM education_textbooks WHERE source_status <> 'ready') OR
           EXISTS (SELECT 1 FROM education_book_jobs WHERE status IN ('queued','running')) OR
           EXISTS (SELECT 1 FROM education_book_job_attempts) OR
           EXISTS (SELECT 1 FROM education_textbooks WHERE source_snapshot_prefix LIKE '%%/source/attempts/%%') THEN
          RAISE EXCEPTION '084 rollback requires settled compatible sources and explicit preservation of attempt history';
        END IF;
      END $$;
      DROP TRIGGER book_attempt_ledger ON education_book_job_items;
      DROP FUNCTION education_book_attempt_ledger();
      DROP TABLE education_book_job_phase_spans,education_book_job_attempts,education_book_creation_requests;
      ALTER TABLE education_book_job_items DROP COLUMN execution_phase,DROP COLUMN queued_at;
      ALTER TABLE education_book_jobs DROP COLUMN previous_job_id,DROP COLUMN round_accepted_at,DROP COLUMN request_round;
      ALTER TABLE education_textbooks DROP CONSTRAINT book_source_ready_complete,DROP CONSTRAINT book_source_prefix_shape,
        DROP COLUMN source_status,DROP COLUMN source_frozen_at,DROP COLUMN selected_source,DROP COLUMN preparation_descriptor,
        ALTER COLUMN source_content_sha256 SET NOT NULL,ALTER COLUMN source_size_bytes SET NOT NULL,
        ALTER COLUMN source_snapshot_prefix SET NOT NULL,ALTER COLUMN source_markdown_key SET NOT NULL;
      ALTER TABLE education_textbooks ADD CONSTRAINT education_textbooks_check
        CHECK (source_snapshot_prefix='education/' || household_id::text || '/textbooks/' || textbook_id::text || '/source/');
    """)
