"""Install the recursive JSONB patch function used by model preferences."""

from alembic import op


revision = "054_jsonb_deep_merge"
down_revision = "053_model_preference"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE OR REPLACE FUNCTION jsonb_deep_merge(a jsonb, b jsonb)
        RETURNS jsonb
        LANGUAGE plpgsql
        IMMUTABLE
        STRICT
        AS $$
        DECLARE
            merged jsonb;
            k text;
        BEGIN
            IF jsonb_typeof(a) <> 'object' OR jsonb_typeof(b) <> 'object' THEN
                RETURN b;
            END IF;
            merged := a;
            FOR k IN SELECT jsonb_object_keys(b) LOOP
                IF b -> k = 'null'::jsonb THEN
                    merged := merged - k;
                ELSIF jsonb_typeof(b -> k) = 'object' THEN
                    merged := jsonb_set(
                        merged,
                        ARRAY[k],
                        jsonb_deep_merge(
                            CASE WHEN jsonb_typeof(merged -> k) = 'object'
                                 THEN merged -> k ELSE '{}'::jsonb END,
                            b -> k
                        ),
                        true
                    );
                ELSE
                    merged := jsonb_set(merged, ARRAY[k], b -> k, true);
                END IF;
            END LOOP;
            RETURN merged;
        END;
        $$
    """)


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS jsonb_deep_merge(jsonb, jsonb)")
