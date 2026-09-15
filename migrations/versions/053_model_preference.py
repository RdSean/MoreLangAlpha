"""Move model-specific preference keys into a dedicated JSONB column."""

from alembic import op


revision = "053_model_preference"
down_revision = "052_in_flight_credits"
branch_labels = None
depends_on = None

MOVED_KEYS = (
    "preferred_model",
    "preferred_flash_model",
    "compaction_model",
    "summarization_model",
    "fetch_model",
    "fallback_models",
    "custom_models",
    "custom_providers",
    "compaction_profile",
    "reasoning_effort",
    "fast_mode",
    "prompt_guidance",
)
_KEY_ARRAY = "ARRAY[" + ", ".join(f"'{k}'" for k in MOVED_KEYS) + "]::text[]"


def upgrade() -> None:
    op.execute("""
        ALTER TABLE user_preferences
        ADD COLUMN IF NOT EXISTS model_preference JSONB NOT NULL DEFAULT '{}'::jsonb
    """)
    op.execute(f"""
        UPDATE user_preferences p
        SET
            model_preference = COALESCE(p.model_preference, '{{}}'::jsonb) || COALESCE(
                (
                    SELECT jsonb_object_agg(e.key, e.value)
                    FROM jsonb_each(COALESCE(p.other_preference, '{{}}'::jsonb)) e
                    WHERE e.key = ANY({_KEY_ARRAY})
                ),
                '{{}}'::jsonb
            ),
            other_preference = COALESCE(p.other_preference, '{{}}'::jsonb) - {_KEY_ARRAY},
            updated_at = NOW()
        WHERE jsonb_exists_any(COALESCE(p.other_preference, '{{}}'::jsonb), {_KEY_ARRAY})
    """)


def downgrade() -> None:
    op.execute("""
        UPDATE user_preferences p
        SET
            other_preference = COALESCE(p.other_preference, '{}'::jsonb)
                || (p.model_preference - 'profiles'),
            updated_at = NOW()
        WHERE p.model_preference IS NOT NULL AND p.model_preference <> '{}'::jsonb
    """)
    op.execute("ALTER TABLE user_preferences DROP COLUMN IF EXISTS model_preference")
