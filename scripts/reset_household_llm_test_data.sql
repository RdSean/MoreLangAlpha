-- Reset LangAlpha test data after migration 033.
--
-- Usage (supply an explicit test database connection):
--   psql "$DATABASE_URL" \
--     --set=target_db=langalpha_test \
--     --set=confirm_reset=DELETE_LANGALPHA_TEST_DATA \
--     --file scripts/reset_household_llm_test_data.sql
--
-- This script deliberately refuses to run unless target_db exactly matches
-- the connected database, the explicit confirmation phrase is supplied, the
-- schema is at migration 033, and every project table below exists. It does
-- not delete object storage or touch Alembic/LangGraph migration metadata.

\set ON_ERROR_STOP on

\if :{?target_db}
\else
\echo 'Refusing reset: supply --set=target_db=<explicit-test-database-name>.'
\quit
\endif

\if :{?confirm_reset}
\else
\echo 'Refusing reset: supply the explicit confirmation phrase.'
\quit
\endif

SELECT
    current_database() = :'target_db' AS target_matches,
    :'confirm_reset' = 'DELETE_LANGALPHA_TEST_DATA' AS reset_confirmed
\gset

\if :target_matches
\else
\echo 'Refusing reset: target_db does not match the connected database.'
\quit
\endif

\if :reset_confirmed
\else
\echo 'Refusing reset: confirmation phrase is invalid.'
\quit
\endif

SELECT EXISTS (
    SELECT 1 FROM alembic_version WHERE version_num = '033'
) AS household_pool_schema_ready
\gset

\if :household_pool_schema_ready
\else
\echo 'Refusing reset: migrate this project database to revision 033 first.'
\quit
\endif

WITH expected(table_name) AS (
    VALUES
        ('automation_executions'),
        ('automations'),
        ('checkpoint_blobs'),
        ('checkpoint_writes'),
        ('checkpoints'),
        ('conversation_feedback'),
        ('conversation_queries'),
        ('conversation_responses'),
        ('conversation_threads'),
        ('conversation_usages'),
        ('education_assets'),
        ('education_chapter_questions'),
        ('education_households'),
        ('education_learning_answers'),
        ('education_learning_progress'),
        ('education_learning_spaces'),
        ('education_memberships'),
        ('education_processing_jobs'),
        ('education_task_material_assets'),
        ('education_task_reviews'),
        ('education_task_rules'),
        ('education_task_submission_assets'),
        ('education_task_submissions'),
        ('education_tasks'),
        ('education_teaching_archive_staging'),
        ('education_teaching_attempts'),
        ('education_teaching_events'),
        ('education_teaching_jobs'),
        ('education_teaching_package_chapters'),
        ('education_teaching_package_questions'),
        ('education_teaching_packages'),
        ('education_textbook_assignments'),
        ('education_textbook_chapters'),
        ('education_textbook_publications'),
        ('education_textbook_sources'),
        ('education_textbook_versions'),
        ('education_textbooks'),
        ('hook_outbox'),
        ('local_auth_accounts'),
        ('local_auth_sessions'),
        ('provenance_records'),
        ('provenance_result_bodies'),
        ('store'),
        ('student_llm_preferences'),
        ('subagent_runs'),
        ('subagent_tasks'),
        ('user_api_keys'),
        ('user_mcp_servers'),
        ('user_oauth_tokens'),
        ('user_preferences'),
        ('users'),
        ('workspace_files'),
        ('workspace_mcp_servers'),
        ('workspace_mcp_tool_schemas'),
        ('workspace_vault_secrets'),
        ('workspaces')
)
SELECT count(*) = (SELECT count(*) FROM expected) AS all_project_tables_present
FROM expected
WHERE to_regclass(format('public.%I', table_name)) IS NOT NULL
\gset

\if :all_project_tables_present
\else
\echo 'Refusing reset: required project tables are missing.'
\quit
\endif

BEGIN;

TRUNCATE TABLE
    automation_executions,
    automations,
    checkpoint_blobs,
    checkpoint_writes,
    checkpoints,
    conversation_feedback,
    conversation_queries,
    conversation_responses,
    conversation_threads,
    conversation_usages,
    education_assets,
    education_chapter_questions,
    education_households,
    education_learning_answers,
    education_learning_progress,
    education_learning_spaces,
    education_memberships,
    education_processing_jobs,
    education_task_material_assets,
    education_task_reviews,
    education_task_rules,
    education_task_submission_assets,
    education_task_submissions,
    education_tasks,
    education_teaching_archive_staging,
    education_teaching_attempts,
    education_teaching_events,
    education_teaching_jobs,
    education_teaching_package_chapters,
    education_teaching_package_questions,
    education_teaching_packages,
    education_textbook_assignments,
    education_textbook_chapters,
    education_textbook_publications,
    education_textbook_sources,
    education_textbook_versions,
    education_textbooks,
    hook_outbox,
    local_auth_accounts,
    local_auth_sessions,
    provenance_records,
    provenance_result_bodies,
    store,
    student_llm_preferences,
    subagent_runs,
    subagent_tasks,
    user_api_keys,
    user_mcp_servers,
    user_oauth_tokens,
    user_preferences,
    users,
    workspace_files,
    workspace_mcp_servers,
    workspace_mcp_tool_schemas,
    workspace_vault_secrets,
    workspaces
RESTART IDENTITY;

COMMIT;

\echo 'LangAlpha test data reset completed.'
