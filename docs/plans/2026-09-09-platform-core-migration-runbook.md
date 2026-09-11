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

## Configuration composition checkpoint (2026-09-09)

- Restored the remote `market_watch` feature catalog and its deployment config,
  including market/news provider chains, OHLCV TTLs and market-watch tuning.
  Local `channels`, education timeouts and other business-specific settings
  remain in `InfrastructureConfig` and `config.yaml`.
- Added the optional local-session `OptionalUserId` dependency required by the
  merged Skills management route without replacing the local Cookie auth path.
- Corrected the MCP route to import discovery rows from the dedicated
  `mcp_tool_schemas` module and added the startup `bundle_owners` snapshot used
  by runtime enforcement.
- Verified 93 focused configuration, bundled-plugin, Egress-session-binding and
  Skills-delivery tests in the isolated test container. The container was
  temporarily supplemented with `quickjs-rs` and `wechatbot-sdk`; these are
  already declared project dependencies and no credentials were committed.
- Full unit-test collection now succeeds (`7139 collected, 8 deselected`). The
  local X MCP server uses the standalone `fastmcp` package because MCP 2.x no
  longer exports `mcp.server.fastmcp`; sandbox defaults continue to pin MCP 1.x
  for third-party MCP entrypoints. One legacy local assertion still expects
  literal HTTP headers to be masked, while the migrated platform contract
  intentionally echoes non-secret literals so connector forms can round-trip.
- PTC/Flash request preparation now passes resolved user/workspace Skill command
  aliases and the effective per-turn Skill set into slash-command detection and
  metadata serialization; the focused request-preparation and Skill command
  suite passed (`119 passed`).
- `056_workspace_file_blobs` remains intentionally deferred. The current branch
  still persists workspace file bytes inline in PostgreSQL; unconnected blob and
  persistence modules are not part of this checkpoint.

## Runtime binding checkpoint (2026-09-09)

- Sandbox asset manifests now accept the managed user Skill view, disabled
  builtin Skills and optional scoped data-service tokens. Token and Skill
  changes participate in content-versioned syncs; local education-managed
  sessions remain untouched.
- Workspace session acquisition now accepts a per-turn Skill delivery
  signature, bypassing the warm sync cooldown when a user/workspace Skill view
  changes. PTC chat passes this signature into session acquisition.
- MCP resolution now carries connector binding plans. OAuth-connected servers
  synchronize relay grants/JWTs before composite installation; discovered tool
  schemas are split into sandbox wrappers and direct-call entries using one
  policy source. Non-OAuth and legacy test sessions retain the prior path.
- Added the atomic sandbox relay credential writer and token manifest upload
  hooks required by the runtime. `056_workspace_file_blobs` and its seven
  untracked persistence helpers remain excluded from commits.
- Focused verification: `171 passed` across sandbox MCP sync, WorkspaceManager
  MCP, Skills commands and chat request preparation.

## Host development mode (2026-09-10)

The application can run on the host against the isolated infra containers. The
Compose service names in `.env` do not resolve from the host, so the launcher
overrides the four connection values:

```bash
# backend (host, port 18000)
DB_HOST=127.0.0.1 DB_PORT=15432 \
REDIS_URL='redis://:redis@127.0.0.1:16379/0' \
STORAGE_ENDPOINT_URL='http://127.0.0.1:19000' \
SERVER_BASE_URL='http://localhost:18000' \
PDF_RENDER_INTERNAL_BASE='http://127.0.0.1:18000' \
uv run python server.py --reload --host 0.0.0.0 --port 18000

# frontend (host, port 15177 — 5177 belongs to the wechat-ilink-bot worktree)
VITE_PROXY_BACKEND='http://localhost:18000' pnpm dev --host 0.0.0.0 --port 15177
```

`REDIS_URL` stays commented in `.env`: the Compose default resolves it to the
`redis` service, which is what the containerized backend needs.

## Capability slice checkpoint (2026-09-10)

The bundled plugins previously restored in `plugins/` were not runnable on
their own — they import the shared `mcp_servers/` helpers and the financial data
layer. Restored from `origin/main`:

- `mcp_servers/_browser.py`, `_envelope.py`, `_extract.py`, `_schemas.py`,
  `_yf_common.py`, `AGENT_CONTRACT.md`
- `src/data_client/` (fmp, ginlix_data, tickertick, yfinance providers)
- `src/market_protocol/` (required by `src/data_client`)
- `src/server/services/brokerage_tool_overlays.py` (required by
  `mcp_tool_split.build_direct_entries`)

Two MCP 2.x compatibility gaps were fixed at the same time:

- `mcp_servers/_bootstrap.py` now exports the `MCPServer` shim (mcp 2.x
  `mcp.server.mcpserver` with the 1.x `fastmcp.FastMCP` fallback) instead of only
  inserting the repo root on `sys.path`.
- `MCPRegistry._discover_tools` reads `tool.input_schema` (mcp 2.x) with an
  `inputSchema` fallback.

The local `scrapling` stdio server is disabled in `agent_config.yaml`: the
pinned `scrapling==0.4.7` CLI imports `mcp.server.fastmcp`, which mcp 2.0
removed. The bundled `alternative_data` `scrape` server drives the same
scrapling tiers through `mcp_servers/_browser.py`.

Verified on the host stack: 10 MCP servers and 61 tools registered at startup
with no connection failures; `/health` returns 200 and the frontend serves 200
on `15177`. Database is at `055_tool_denylist (head)`.

## MCP surface parity checkpoint (2026-09-10)

The Connectors tab loaded empty because the platform MCP surface had not been
ported, not because of a runtime fault. Fixed in this pass:

- `src/server/app/mcp_catalog.py` replaced with the platform router (16 routes:
  catalog CRUD, `/servers/import`, `/servers/{name}/binding`, `/builtin-servers`,
  `/brokerages`, icon routes, tools listings).
- `src/server/app/mcp_servers.py` replaced with the platform workspace router.
  The local education guard is preserved by re-attaching
  `_require_nonstudent_mcp_access` as a router-level dependency, which the
  platform version does not have.
- `src/server/database/pool.py`: `get_db_connection(conn=None)` now yields a
  caller-supplied connection. Without it every migrated database module raised
  `TypeError` and the whole catalog answered 500.
- Binding columns and consent: local migrations
  `056_mcp_tool_binding` (ports `041_tool_binding`) and
  `057_brokerage_capabilities` (ports the remaining half of
  `036_brokerage_capabilities`; `policy_required` already arrived via
  `055_tool_denylist`). `tool_binding.py`, `egress_grants.py`,
  `relay_jwt.py` and `tool/error_handling.py` replaced with the platform
  versions.
- Frontend catalogs: the `plugins`, `mcp` and `vault` namespaces were merged
  from `origin/main` (origin wins on conflicts, local-only keys survive). The
  local financial-language guard now excludes `plugins.brokerages.capabilities`,
  which deliberately ships the `watchlists`/`alerts` consent labels.

Verification: `tests/unit/server/app/test_mcp_catalog.py`,
`test_mcp_servers.py` and `tests/unit/server/models/test_mcp_server_models.py`
went from 58 failures to `264 passed`; frontend
`src/pages/Plugins` + `src/hooks/__tests__` + locales report `359 passed,
1 failed` with the failure being the `TestStorage` artifact above. Backend unit
collection: `7195/7203 collected`, no import errors. Live endpoints
`/api/v1/mcp/servers`, `/builtin-servers`, `/brokerages`, `/api/v1/plugins` and
`/api/v1/skills` all answer 200, and the startup registry still freezes 10
servers / 61 tools.

## Skills-source alignment checkpoint (2026-09-10)

The platform model is that shipped Skills come from `plugins/*/skills` bundles
plus the operator's `user_skills_dir`; a repo-root `skills/` directory is not
part of it. This branch still carried one, which made `SkillsConfig` depend on
the working directory and kept twelve stale copies of bundle Skills — the
local rewrites had removed financial wording the platform bundles keep.

- This deployment's own two Skills (`book-to-skill`, `the-knowledge-guy`) moved
  into a new bundle, `plugins/langalpha_local/`, so they still ship without
  shadowing any vendor bundle. Nothing resolves against `cwd` any more.
- The repo-root `skills/` directory and the stale `skills-lock.json` artifact
  were removed. The twelve duplicates now come from the bundles that already
  declare them, with the platform wording restored — consistent with retaining
  the financial bundles until the dependency-ordered removal pass.
- `host_skill_dirs` / `SkillsConfig` / the loaders took the platform shape
  (`user_skills_dir` only). `deploy/Dockerfile.dev`, `deploy/Dockerfile.backend`
  and `docker-compose.yml` now ship/mount `plugins/` instead of `skills/`.
- The two education services that staged these Skills from the repo path
  (`education_textbooks._managed_skill_hash`,
  `education_teaching_storage.stage_managed_teaching_skills`) now resolve them
  through `host_skill_dirs`, so they follow the bundle.
- Registry entries for the two Skills were restored in
  `ptc_agent/agent/middleware/skills/registry.py` — they had been lost when the
  registry was realigned with the platform version.

Superseded finance-free guards from the earlier removal phase were retired with
this change, because they assert a state the branch deliberately no longer
holds: `tests/unit/ptc_agent/agent/test_generic_tool_boundary.py`,
`tests/unit/server/services/test_generic_startup_services.py`,
`tests/unit/migrations/test_generic_migration_chain.py`, and the
source-package half of `tests/unit/server/app/test_generic_router_registration.py`.
The dependency-ordered removal pass should restore them from git history.

Verified: `tests/unit/config` 245, `tests/unit/core`+observability+ci 552,
`tests/unit/llms`+tools+utils 1240, `tests/unit/middleware` 484,
`tests/unit/ptc_agent` 707, `tests/unit/server/services` 1208,
`tests/unit/server/app`+handlers 1413, `tests/unit/server/database`+models+utils
765, remaining root-level unit tests 125 — all passing.

## Remaining work

> The task-by-task plan for finishing the merge lives in
> `docs/plans/2026-09-10-post-merge-completion.md`. Task 1 (managed-textbook
> hooks) is done; the plan file carries the status of each task, so read it
> before starting the next one — it is the durable context for this work.

1. Direct MCP tools are ported but not yet wired. The modules now exist
   (`ptc_agent/agent/middleware/direct_mcp.py`, `egress/direct_tools.py`,
   `egress/flash_binding.py`, `egress/grant_resync.py`) and
   `session.direct_mcp_tools` is populated, but `build_ptc_graph_with_session`
   and `create_agent` still take no `direct_mcp=`, so every MCP tool reaches
   the model as a sandbox wrapper. Flash still cannot run MCP tools at all
   until that lands.
2. **Migration renumbering.** The local chain owns `035`–`045`, so upstream's
   post-fork migrations land after it rather than under their upstream numbers:

   | upstream | local | note |
   |---|---|---|
   | `035_jsonb_deep_merge` | `054_jsonb_deep_merge` | |
   | `036_brokerage_capabilities` | `057_brokerage_capabilities` | |
   | `038_tool_denylist` | `055_tool_denylist` | |
   | `039_workspace_file_blobs` | `058_workspace_file_blobs` | `workspace_file_blobs` registry, the `blob_sha256`/`pack_sha256`/`kind`/`symlink_target`/`pack_offset` columns, `workspaces.files_restore_incomplete_at`, partial indexes |
   | `040_direct_tools` | `059_direct_tools` | `sandbox_egress_grants.tool_direct_only` + `mcp_config_version` bump |
  | `041_tool_binding` | `056_mcp_tool_binding` | |
  | `037_free_webull_name` | **skipped on purpose** | one-shot data repair for user MCP servers already sitting on the `webull` name; it builds on upstream's `030`/`032`, which this chain never ran. No row here holds such a name; port it as `060` if that ever changes. |
   | *(local 001 / 005 / 007 edits)* | `060_restore_finance_schema` | the local baseline had dropped `user_preferences.risk_preference` / `investment_preference` and the `watchlists`, `watchlist_items`, `user_portfolios`, `market_insights` tables; local `005`/`007` are empty stubs, so their index and VARCHAR conversion are folded into `060` |

   Verified on the isolated stack (`15432`): `057 → 058 → 059`, then
   `059 → 057 → 059`; afterwards `workspace_files` and `sandbox_egress_grants`
   carry the new columns and indexes.
3. Workspace file bytes now travel through content-addressed object storage:
   the persistence layer (`backup`/`restore`/`_rows`/`blobs`/`resolve`) writes
   `blob_sha256` pointers and `WorkspaceFileGCService` reaps condemned rows.
   `scripts/ops/` carries the companions — `backfill_workspace_file_blobs.py`
   (both directions), `report_orphan_blobs.py`, and the shared `_db.py`.
4. Connector/OAuth consent end-to-end still needs a live OAuth connection, but
   host-side egress now works. The machine's Clash Verge profile was switched
   from fake-IP to real-IP DNS with TUN on, so `pin_public_url` resolves and
   dials public addresses again — the earlier failure was the guard rejecting
   `198.18.0.0/15` fake addresses, not a code defect. Verified: pinned GETs
   reach all four brokerage endpoints (405/401/404/401, i.e. transport works),
   moomoo's `/.well-known/oauth-protected-resource` and
   `/.well-known/oauth-authorization-server` both answer 200, and plugin plus
   brokerage icon routes return real images.
5. `channel-gateway` (WeChat iLink worker) is not part of the host launcher
   above; start it separately (`python -m src.server.services.channels.worker`)
   when testing channel behaviour.
6. Financial capability removal stays a later, dependency-ordered pass
   (`bundle manifest → backend APIs → MCP servers/tools → Skills → frontend →
   migrations/data`), after the platform baseline is green.
7. Local test-infra divergences worth revisiting: `web/src/test/setup.ts`
   installs a hand-rolled `TestStorage` that is not a real `Storage` instance,
   so `connectReturn.test.ts`'s `vi.spyOn(Storage.prototype, …)` case cannot
   intercept it. The catalog command denylist (`bash`/`sh`/`curl`/`rm`) also
   stays local-only and is asserted by the ported catalog test.

## End-to-end verification (2026-09-10)

Environment: host backend `uv run python server.py --host 0.0.0.0 --port 18000`
against the isolated stack (`15432/16379/19000`), frontend on `15177`,
`SANDBOX_PROVIDER=docker`, image `langalpha-sandbox:latest`.

- Startup is clean: `PTC Agent configuration loaded successfully`, 12 MCP servers
  (10 bundled + 2 added), registry frozen at 61 tools, checkpointer healthy
  (`pool_min=1 pool_max=25`), `/health` 200.
- `agent_config.yaml` needed one fix on the way: it still enabled the subagent
  name `analyst`, which upstream renamed to `equity-analyst`. With it enabled,
  PTC Agent initialisation failed outright.
- `POST /api/v1/workspaces` created workspace
  `1957a6e6-…` with sandbox `docker-9d2ebd6f5759`; container
  `langalpha-sandbox-docker-9d2ebd6f5759` came up on `langalpha-sandbox:latest`,
  and the asset sync uploaded 10 MCP servers / 61 tools plus the skill tree.
- Turn 1 (plain question) → `conversation_responses.status=completed`, assistant
  answered `pong`, `context_window` reported 17 494 input tokens, one
  `conversation_usages` row.
- Turn 2 (write + read a file in the sandbox) → `completed` with
  `tool_calls` / `tool_call_result` / `artifact` / `provenance` events; the
  artifact payload is `Write work/sandbox_check/hello.txt` with content
  `step-ok`.
- `POST /workspaces/{id}/stop` synced the sandbox into the database: 200+
  `workspace_files` rows with `kind` set (`file`/`dir`), `pack_sha256` non-null
  and **no** inline content, plus a `workspace_file_blobs` registry row
  (4 824 172 bytes). That exercises the whole blob path — pack, upload,
  register — which is what made `058` mandatory rather than optional.
- Still open: a user-level (non-bundled) MCP connector end to end.
  `workspace_mcp_tool_schemas` stays empty until one is added to the workspace;
  the bundled stdio servers are delivered through the frozen registry instead.

### Routers the local `setup.py` had dropped

The hand-merged `setup.py` inherited the local "finance removed" router list, so
nine upstream routers were unregistered even though their modules were present:
`market_data`, `bars`, `watchlist`, `portfolio`, `news`, `calendar`,
`sec_proxy`, `insights`, `chart_annotations`, plus the ginlix-data
`market_data_ws` proxy (its disabled-status stub answers 200 when
`GINLIX_DATA_URL` is unset). All are registered again — 258 route paths, up
from 250 — and the guard test that asserted their absence now asserts their
presence until the removal pass flips it back.

### The product frontend

`web/src` is still ~400 files behind upstream, and most of that gap is the
upstream product screens (Dashboard, ChatAgent, MarketView, Onboarding, Login),
the finance chart stack (`lib/bars`, `lib/quotes`) and the Supabase auth client
(this branch runs first-party local sessions instead). Those replace the local
product rather than restore a capability, so they remain out of scope.

**Model tuning is done** (2026-09-11): the whole Settings-side surface came over
— `lib/modelTuning`, `lib/modelPreferences`, `hooks/useModelProfile`,
`components/model/{AccountTuningDefaults,PerModelMatrix,CompactionProfilePicker,FallbackModelsPicker}`,
the upstream `ModelTab`/`ModelTierConfig`/setup steps, the shared
`tests/fixtures/{tuning_precedence,reasoning_clamp}.json` contract and both
locales. This also fixed a real bug: the local tab wrote every model key into
`other_preference` while the merged server re-routes those keys into
`model_preference` on write only, so a save followed by a reload showed
defaults.

**Still local: the composer cluster** — `components/ui/chat-input.tsx` plus its
`modelMenu`/`parts`/`toolbar`/`types` siblings. It keeps reasoning effort and
fast mode in `localStorage` and sends them per turn; the persisted account- and
per-model tuning therefore applies whenever the composer has no value of its
own for that model, and a composer choice still outranks it (which is the
documented top rung). Porting it means a 3-way merge across that whole cluster
on top of the family-model menu logic it already carries, so it is its own task.
