# Platform Core Migration Runbook

> Execution branch: `feature/platform-core-migration` (derived from `feature/wechat-ilink-bot`).

## Objective

Migrate the `origin/main` platform core (Plugins, MCP, Skills, Vault/OAuth and scope/inheritance management) while preserving local education, household, WeChat iLink/channel and other business logic. Financial bundles are initially retained only as optional validation fixtures and may be removed later by an explicit dependency-ordered cleanup.

## Infrastructure contract

- Use only the new worktree: `/Users/seanlee/.config/superpowers/worktrees/langalpha/platform-core-migration`.
- Copy required configuration values from the `wechat-ilink-bot` `.env`; never commit or print secrets.
- Use a separate Compose project and host ports:
  - backend `18000`
  - frontend `15177`
  - Postgres `15432`
  - Redis `16379`
  - MinIO API `19000`
  - MinIO console `19001`
- Use only this worktree's `deploy/volumes` paths. Do not reuse, enumerate, delete, or migrate old debug volumes or MinIO objects.
- Keep the existing `wechat-ilink-bot` stack available until the new stack passes smoke tests. Never remove unknown containers, volumes, networks, or images.

## Database compatibility rules

Local migrations `025`–`045` are real product migrations (education, household, channel gateway, document library, etc.) and must remain unchanged. Remote migrations `025`–`039` have conflicting revision IDs and must never be copied verbatim.

The current execution baseline already contains local `045_add_document_library` (`045 <- 044`). Create a new chain after that actual head, using unique descriptive revision IDs and preserving semantic order, for example:

```text
045_add_document_library
 └─ 046_mcp_platform_core
    └─ 047_user_skills
       └─ 048_builtin_mcp_disables
          └─ 049_agent_plugins
             └─ 050_plugin_owned_secrets
                └─ ...
```

Before each migration:

1. Run the local chain through the actual local head (`045` in this worktree) on a disposable database.
2. Assert local education/family/channel tables and constraints still exist.
3. Compare the remote SQL against local table/column/JSONB/FK/index definitions.
4. Add only the missing schema and preserve local constraints.
5. Test `upgrade head`, `current`, and bounded downgrade/upgrade on the disposable database.

Defer brokerage-only migrations (`free_*_brokerage`, Moomoo/Webull names and capability tables) unless the selected validation bundle requires them. Do not skip a migration dependency silently; replace it with a compatible no-op only when its schema contract is proven unnecessary.

## Migration order

1. Isolated Compose/env and health checks.
2. Local schema baseline through `044` and business regression checks.
3. MCP resolved-set, catalog/import, schema cache and discovery lifecycle.
4. User/workspace Skills CRUD, archive storage and sandbox sync.
5. User/workspace Vault and shared MCP invalidation.
6. Plugin manifest/discovery/install/update/bindings/export lifecycle.
7. OAuth and optional connector capability controls.
8. Generic Plugins frontend (MCP, Skills, Vault, scope and bulk actions).
9. Optional financial bundles for validation.
10. Only after a green baseline, remove financial capabilities in dependency order.

Each substantial verified phase gets focused tests, a Chinese `CHANGELOG.md` entry, and one atomic commit. Do not mix migration-chain rewrites with unrelated UI or business changes.

## Financial bundle rules

Initially it is acceptable to bring back `langalpha_research`, `langalpha_deliverables`, market-data/yfinance and the minimal brokerage/secret pieces needed for validation. Bundle registration must be capability-driven.

Bundled plugins are read from repository files. UI disable suppresses runtime registration but does not delete source code, MCP tools, Skills, manifests or frontend components. UI uninstall only removes user-installed plugin rows/components; it does not remove bundled files.

When removing financial functionality later, use:

```text
bundle registration/manifest
 → backend APIs and registries
 → MCP server implementations/tools
 → Skills and references
 → frontend routes/components/icons/tests
 → financial-only migrations and data cleanup
```

After each removal, verify `/api/v1/plugins`, `/api/v1/mcp/servers`, `/api/v1/skills` and the generic Plugins page still work with no financial bundle present.

## Long-running task checkpoints

- Before a risky change: record `git status`, branch, commit, `alembic heads`, Compose project and port map.
- After every phase: run focused tests and record the result in the commit message/plan notes.
- If a test fails, classify it as baseline, migration compatibility, platform-core, or optional-finance before changing code.
- Never resolve Alembic conflicts by deleting local migrations or using destructive database commands.
- Never copy old `.env` values into tracked files; use the ignored worktree `.env` only.
- Never claim completion without verification evidence from the isolated stack.

## Progress checkpoint (2026-09-09)

- Worktree/branch: `feature/platform-core-migration`, based on
  `feature/wechat-ilink-bot`.
- Isolated Compose project: `langalpha-platform-core-migration`.
- Host ports: backend `18000`, frontend `15177`, Postgres `15432`, Redis
  `16379`, MinIO API/console `19000/19001`.
- The copied `.env` is ignored and must remain untracked. The old WeChat stack
  and its data have not been stopped, modified, or migrated.
- Local migration baseline `001–045` passed on the empty isolated database;
  local education, household, channel and document-library tables remain
  present.
- `046_mcp_platform_core` passed focused tests and upgrade/downgrade/upgrade;
  it adds user Vault, MCP OAuth/schema, egress state and
  `user_mcp_servers.enabled`.
- `047_user_skills` passed focused tests and upgrade/downgrade/upgrade; it adds
  user/workspace skill rows, archive constraints/indexes and inherited-skill
  disable storage.
- `048_builtin_mcp_disables` passed focused tests and upgrade/downgrade/upgrade;
  it adds account-wide builtin MCP disable rows.
- Database is currently at `048_builtin_mcp_disables`.
- Commits for the completed rounds: `dc926492`, `f59cd9ad`, `36280b9f` (plus
  documentation checkpoints `17902fd2`, `dc0322ad`, `3e5cf1f5`, `7a74e433`).
- Next task: port remote `028_agent_plugins` as local `049_agent_plugins`.

The next completed checkpoint now includes `049_agent_plugins` and
`050_plugin_owned_secrets`; the isolated database is at
`050_plugin_owned_secrets`. Both migrations passed focused tests and bounded
upgrade/downgrade/upgrade checks. User plugin ownership uses RESTRICT on MCP
and Skills, while Vault plugin ownership intentionally uses SET NULL so a
plugin uninstall cannot be blocked by a retained credential.

`051_account_disable_kind` is also complete. It extends account-wide disable
rows with `kind='server'|'bundle'`; legacy rows are backfilled as `server`, and
the isolated database is now at `051_account_disable_kind`. The migration has
no brokerage schema dependency despite its later position in the remote chain.

The next checkpoint `052_in_flight_credits` is complete. It adds additive,
non-negative in-flight credit columns and partial indexes to root and subagent
runs; focused tests and `051 -> 052 -> 051 -> 052` verification passed. The
database is now at `052_in_flight_credits`.

`053_model_preference` is complete. It adds the dedicated model preference
JSONB column, moves only model-related keys from `other_preference`, preserves
feature/channel keys, and passes focused tests plus live data and
`052 -> 053 -> 052 -> 053` checks. The runtime read-path remains intentionally
unchanged until the corresponding service migration is ported.

`054_jsonb_deep_merge` is complete. It installs the recursive JSONB merge
function used by the new model preference shape; live PostgreSQL verification
covered nested merge and JSON null deletion, and the bounded
`053 -> 054 -> 053 -> 054` path passed. The database is now at
`054_jsonb_deep_merge`.

`055_tool_denylist` is complete. It ports the MCP egress allowlist-to-denylist
expand phase while retaining the old column for rolling compatibility and
supplying the deferred finance migration's `policy_required` prerequisite.
Upgrade preserves legacy allowlists and bumps OAuth workspace config versions;
downgrade writes an empty allowlist before removing the denylist so rollback is
fail-closed. Focused tests and live `054 -> 055 -> 054 -> 055` verification
passed. The isolated database is now at `055_tool_denylist`.

## Platform surface checkpoint (2026-09-09)

The first platform surface batch is now present on the migration branch:
Plugins, MCP OAuth, user Vault, egress relay, plugin/Skills services and their
database accessors are restored from `origin/main`; local education, household,
channel and document-library routes remain registered. The frontend Plugins
page is reachable at `/plugins`, with `/connectors` retained as a redirect.
Frontend type-check and production build pass. Remote workspace blob migration
is intentionally deferred because this branch still persists workspace file
bytes inline and has no blob-backed read/write path.

The PTC runtime alignment batch is also applied: MCP tool generation/setup and
client runtime now consume the origin trust boundary and OAuth binding fields;
Skills middleware/registry and sandbox sync consume user/workspace skill rows.
`MCPServerConfig` accepts user-tier servers and `oauth_connection_id`. Static
Python compilation passed. FastAPI-level backend tests are pending because the
current backend image does not contain the local branch's `argon2` dependency.
