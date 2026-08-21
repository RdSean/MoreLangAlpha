"""Use the household creator as the shared model owner.

Revision ID: 033
Revises: 032
"""

from alembic import op


revision = "033"
down_revision = "032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE education_households
            ADD COLUMN model_owner_user_id VARCHAR(255)
                REFERENCES users(user_id) ON DELETE RESTRICT
        """
    )
    op.execute(
        """
        UPDATE education_households AS households
        SET model_owner_user_id = (
            SELECT memberships.user_id
            FROM education_memberships AS memberships
            WHERE memberships.household_id = households.household_id
              AND memberships.role = 'parent'
            ORDER BY memberships.created_at ASC
            LIMIT 1
        )
        WHERE households.model_owner_user_id IS NULL
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM education_households
                WHERE model_owner_user_id IS NULL
            ) THEN
                RAISE EXCEPTION 'Every education household must have a parent model owner';
            END IF;
        END $$
        """
    )
    op.execute(
        """
        ALTER TABLE education_households
            ALTER COLUMN model_owner_user_id SET NOT NULL
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION validate_education_household_model_owner()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $fn$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM education_memberships
                WHERE household_id = NEW.household_id
                  AND user_id = NEW.model_owner_user_id
                  AND role = 'parent'
            ) THEN
                RAISE EXCEPTION 'Household model owner must be a parent member of the same household';
            END IF;
            RETURN NEW;
        END;
        $fn$
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION validate_education_household_owner_membership()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $fn$
        DECLARE
            affected_household UUID;
        BEGIN
            affected_household := COALESCE(NEW.household_id, OLD.household_id);
            IF EXISTS (
                SELECT 1 FROM education_households AS households
                WHERE households.household_id = affected_household
                  AND NOT EXISTS (
                      SELECT 1
                      FROM education_memberships AS memberships
                      WHERE memberships.household_id = households.household_id
                        AND memberships.user_id = households.model_owner_user_id
                        AND memberships.role = 'parent'
                  )
            ) THEN
                RAISE EXCEPTION 'Household model owner must remain a parent member of the same household';
            END IF;
            RETURN NULL;
        END;
        $fn$
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER education_household_model_owner_check
        AFTER INSERT OR UPDATE OF model_owner_user_id, household_id
        ON education_households
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW
        EXECUTE FUNCTION validate_education_household_model_owner()
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER education_household_owner_membership_check
        AFTER INSERT OR UPDATE OF household_id, user_id, role OR DELETE
        ON education_memberships
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW
        EXECUTE FUNCTION validate_education_household_owner_membership()
        """
    )
    op.execute(
        """
        CREATE TABLE student_llm_preferences (
            user_id VARCHAR(255) PRIMARY KEY
                REFERENCES users(user_id) ON DELETE CASCADE,
            household_id UUID NOT NULL,
            model_key VARCHAR(255) NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            FOREIGN KEY (household_id, user_id)
                REFERENCES education_memberships(household_id, user_id)
                ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE INDEX idx_student_llm_preferences_household_user
        ON student_llm_preferences (household_id, user_id)
        """
    )
    op.execute(
        """
        ALTER TABLE conversation_usages
            ADD COLUMN household_id UUID,
            ADD COLUMN credential_source VARCHAR(32),
            ADD COLUMN model_snapshot JSONB
        """
    )
    op.execute(
        """
        ALTER TABLE conversation_usages
            ADD CONSTRAINT conversation_usages_household_fk
                FOREIGN KEY (household_id)
                REFERENCES education_households(household_id)
                ON DELETE SET NULL
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE conversation_usages
            DROP CONSTRAINT IF EXISTS conversation_usages_household_fk,
            DROP COLUMN IF EXISTS model_snapshot,
            DROP COLUMN IF EXISTS credential_source,
            DROP COLUMN IF EXISTS household_id
        """
    )
    op.execute("DROP INDEX IF EXISTS idx_student_llm_preferences_household_user")
    op.execute("DROP TABLE IF EXISTS student_llm_preferences")
    op.execute("DROP TRIGGER IF EXISTS education_household_model_owner_check ON education_households")
    op.execute("DROP TRIGGER IF EXISTS education_household_owner_membership_check ON education_memberships")
    op.execute("DROP FUNCTION IF EXISTS validate_education_household_owner_membership()")
    op.execute("DROP FUNCTION IF EXISTS validate_education_household_model_owner()")
    op.execute("ALTER TABLE education_households DROP COLUMN IF EXISTS model_owner_user_id")
