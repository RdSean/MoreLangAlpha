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

Local migrations `025`–`044` are real product migrations (education, household, channel gateway, etc.) and must remain unchanged. Remote migrations `025`–`039` have conflicting revision IDs and must never be copied verbatim.

Create a new chain after the local head, using unique descriptive revision IDs and preserving semantic order, for example:

```text
044
 └─ 045_mcp_platform_core
    └─ 046_user_skills
       └─ 047_builtin_mcp_disables
          └─ 048_agent_plugins
             └─ 049_plugin_owned_secrets
                └─ ...
```

Before each migration:

1. Run the local chain through `044` on a disposable database.
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
