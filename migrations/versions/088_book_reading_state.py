"""Per-user reading state and parent lesson Flash conversations."""

from migrations.textbook_ddl import execute_textbook_ddl as execute

revision = "088_book_reading_state"
down_revision = "087_book_token_usage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute("""
        CREATE TABLE education_book_reading_state (
          user_id VARCHAR(255) NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
          textbook_id UUID NOT NULL,
          knowledge_point_id UUID NOT NULL,
          viewed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          asked_at TIMESTAMPTZ,
          conversation_thread_id UUID REFERENCES conversation_threads(conversation_thread_id) ON DELETE SET NULL,
          PRIMARY KEY (user_id, textbook_id, knowledge_point_id),
          FOREIGN KEY (textbook_id, knowledge_point_id)
            REFERENCES education_book_knowledge_points(textbook_id, knowledge_point_id) ON DELETE CASCADE
        );
        CREATE INDEX education_book_reading_thread ON education_book_reading_state(conversation_thread_id);
    """)


def downgrade() -> None:
    execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM education_book_reading_state) THEN
        RAISE EXCEPTION '088 rollback requires preserving reading state';
      END IF;
    END $$;
    DROP TABLE education_book_reading_state;
    """)
