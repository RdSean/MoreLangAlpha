# Migration mapping and compatibility checklist

## Confirmed local baseline

The execution branch is based on `feature/wechat-ilink-bot`, not bare
`local-main`. Its current local migration head is:

```text
045_add_document_library.py: revision 045, down_revision 044
```

The local chain from `025` onward contains education, household, channel
gateway and document-library business logic. These revisions are authoritative
and must not be replaced by remote revisions with the same IDs.

## Remote semantic mapping

| Remote revision | Meaning | Local migration ID | Initial policy |
|---|---|---|---|
| 025 | MCP connector/user vault/oauth/schema/egress base | 046_mcp_platform_core | migrate after 045 |
| 026 | User/workspace Skills | 047_user_skills | migrate after 046 |
| 027 | Builtin MCP disable rows | 048_builtin_mcp_disables | migrate after 047 |
| 028 | Agent Plugins and ownership fan-out | 049_agent_plugins | migrate after 048 |
| 029 | Plugin-owned secrets | 050_plugin_owned_secrets | migrate after 049 |
| 030 | Brokerage reserved-name compatibility | deferred | finance-only |
| 031 | Account disable kind | 051_account_disable_kind | verify dependency on 048 |
| 032 | Moomoo reserved-name compatibility | deferred | finance-only |
| 033 | In-flight credit ledger | 052_in_flight_credits | migrate only if local code lacks equivalent |
| 034 | Model preference | 053_model_preference | verify local preferences first |
| 035 | JSONB deep merge | 054_jsonb_deep_merge | migrate if runtime requires it |
| 036 | Brokerage capabilities | deferred | finance-only |
| 037 | Webull reserved-name compatibility | deferred | finance-only |
| 038 | MCP tool denylist / egress changes | 055_tool_denylist | migrate with MCP core |
| 039 | Workspace file blobs | 056_workspace_file_blobs | only with blob runtime |

The exact IDs may change after inspection, but every new `revision` must be
unique in this repository and every `down_revision` must point to the prior
local migration. Never create a second Alembic head to avoid resolving a
conflict.

## Required checks before SQL porting

- Verify existing `user_mcp_servers`, `workspace_mcp_servers`,
  `workspace_mcp_tool_schemas`, `workspace_vault_secrets`, `user_preferences`,
  `workspace_files` and `workspaces` definitions.
- Compare remote `ALTER TABLE` statements with local columns and constraints.
- Preserve local education/channel/document tables and foreign keys.
- Avoid `DROP ... CASCADE` in compatibility migrations unless the object is
  newly created by that same migration and the downgrade is explicitly tested.
- Run the full local chain to `045` on a disposable database before applying
  any `046+` migration.

## Baseline verification (2026-09-09)

The isolated Compose project `langalpha-platform-core-migration` is running
Postgres on host port `15432`, Redis on `16379`, and MinIO on `19000/19001`.
Using the backend image's preinstalled Alembic client, `upgrade head` completed
from an empty database through local revision `045`. The database reports
`alembic_version = 045`, and the following local/platform-predecessor tables
were confirmed present: `local_auth_accounts`, `education_tasks`,
`channel_bindings`, `document_datasets`, `user_mcp_servers`,
`workspace_mcp_servers`, `workspace_mcp_tool_schemas`, and
`workspace_vault_secrets`.

This proves the local business chain is runnable in the new database and that
the platform migration work must start at a new revision after `045`.

## First platform migration verification (2026-09-09)

The semantic port of remote `025_mcp_connectors` is implemented as
`046_mcp_platform_core` (`046_mcp_platform_core.py`). Focused migration tests
pass, the isolated database upgraded `045 -> 046_mcp_platform_core`, and a
bounded downgrade/upgrade round trip also passes. The database now reports
`046_mcp_platform_core` and contains the user vault, OAuth connection, user
tool-schema and sandbox egress grant tables plus `user_mcp_servers.enabled`.

The semantic port of remote `026_user_skills` is implemented as
`047_user_skills` (`047_user_skills.py`). Focused tests pass, and the isolated
database upgraded `046_mcp_platform_core -> 047_user_skills`; a bounded
downgrade/upgrade round trip also passes. The database reports
`047_user_skills` and contains `user_skills`, `workspace_skill_disables`, the
four per-scope uniqueness indexes, archive/plugin lookup indexes, and the
archive-present check constraint.

The semantic port of remote `027_user_mcp_builtin_disables` is implemented as
`048_builtin_mcp_disables`. Focused tests pass, and the isolated database
completed both upgrade and bounded downgrade/upgrade round trips. The database
reports `048_builtin_mcp_disables` and contains the account-scoped
`user_mcp_builtin_disables` primary-key table.

## Checkpoint index

| Round | Local revision | Verification | Commit |
|---|---|---|---|
| MCP platform base | `046_mcp_platform_core` | focused tests; upgrade and downgrade/upgrade | `dc926492` |
| User/workspace Skills | `047_user_skills` | focused tests; upgrade and downgrade/upgrade | `f59cd9ad` |
| Builtin MCP disables | `048_builtin_mcp_disables` | focused tests; upgrade and downgrade/upgrade | `36280b9f` |

The isolated database is intentionally left at `048_builtin_mcp_disables` for
the next migration round. This checkpoint is the recovery point if a later
schema port fails.

The semantic port of remote `028_agent_plugins` is implemented as
`049_agent_plugins`. Focused tests pass, and the isolated database completed
`048 -> 049` plus a bounded downgrade/upgrade round trip. The migration adds
`user_plugins`, MCP plugin provenance columns/indexes, and RESTRICT ownership
foreign keys for MCP servers and Skills.

The semantic port of remote `029_plugin_owned_secrets` is implemented as
`050_plugin_owned_secrets`. Focused tests pass, and the isolated database
completed `049 -> 050` plus a bounded downgrade/upgrade round trip. The
migration adds `user_vault_secrets.plugin_id`, a composite ownership FK with
`ON DELETE SET NULL (plugin_id)`, and the plugin lookup index. The current
database checkpoint is `050_plugin_owned_secrets`.

The semantic port of remote `031_account_disable_kind` is implemented as
`051_account_disable_kind`. Although the remote chain placed it after a
finance-only revision, this SQL only changes the builtin-disable table and has
no brokerage dependency. Focused tests pass. A live database check confirmed
legacy `(user_id, name)` rows are backfilled as `kind='server'`, while a second
`kind='bundle'` row with the same name is allowed; upgrade and rollback paths
were also exercised. The database checkpoint is now `051_account_disable_kind`.

Final bounded check completed after commit: `051 -> 050 -> 051` succeeded on
the isolated database, which remains at `051_account_disable_kind`.

The semantic port of remote `033_in_flight_credits` is implemented as
`052_in_flight_credits`. Local `conversation_responses` and `subagent_runs` had
no equivalent ledger columns, so this migration is required rather than a
duplicate. Focused tests pass; the isolated database contains the three
in-flight/settled indexes and non-negative checks, and `051 -> 052 -> 051 ->
052` upgrade/rollback verification completed. The checkpoint is now
`052_in_flight_credits`.
