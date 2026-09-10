# Staged core merge — plan and rules

> Rollback point: `checkpoint/pre-core-merge` (created 2026-09-10, points at the
> Skills/bundle alignment commit `8f6f63da`).

## Why staged, and why not `git checkout origin/main -- src`

`src/` has drifted a long way: 748 files locally, 697 upstream, 670 present on
both sides. Measured against the fork point (`4f56db64`, 2026-08-06):

| set | count |
|---|---|
| files changed locally since the fork | 316 |
| files changed upstream since the fork | 305 |
| files changed by **both** sides | 191 |
| files that exist only locally | 78 |
| files that exist only upstream | 27 |

A wholesale checkout would delete the 78 local-only files — education,
documents, WeChat/channel, household and the local email/password auth — and
`src/server/app/setup.py` registers their routers, so the app would not import.
It would also overwrite files that carry local product decisions.

## Classification rules

Every path that both sides changed is filed by rule, in this order:

1. **KEEP** — exists only locally. Never overwritten, never deleted.
   `docs/plans/core-merge-keep-list.txt` (78 paths).
2. **HAND-MERGE** — either the path is user/auth/education/family/channel/
   document/speech related, or the file's **imports** (resolved through the AST,
   not a word match) reach a local-only module, or the local-only features
   import symbols that upstream's version no longer provides.
   `docs/plans/core-merge-hand-merge.txt` (21 paths).
3. **TAKE-ORIGIN** — everything else. `docs/plans/core-merge-take-origin.txt`
   (170 paths), plus the 27 upstream-only files.

The first draft of this classification used a path keyword regex and a textual
mention check, which flagged 103 files — `mcp_oauth/*` matched because "oauth"
contains "auth", and `user_skills/materialize.py` matched because the word
"storage" appears in its docstrings. Both were replaced with exact path
predicates and AST import resolution, which is what drops the count to 21. The
twenty-one are the honest interleaving: the five user files, the config and
setup modules the local features import from, the thread/workspace routes, and
the workspace manager.

The third rule is the one that needs evidence rather than a path pattern: for
every file that local-only modules import from, the required symbols were
compared against upstream's version. Seven files do not satisfy it and are
therefore HAND-MERGE:

| file | symbols upstream no longer provides |
|---|---|
| `src/config/env.py` | `AUTH_COOKIE_SECURE`, `EDUCATION_ASSET_*`, `LOCAL_AUTH_SESSION_TTL_DAYS` |
| `src/config/settings.py` | `VolcengineAsrConfig`, `get_channel_gateway_config`, `get_document_parsing_config`, `get_education_teaching_workflow_timeout`, `get_volcengine_asr_config` |
| `src/server/database/__init__.py` | `channels`, `document_jobs`, `documents` |
| `src/utils/storage/__init__.py` | `upload_bytes`, `get_bytes`, `get_signed_url`, `delete_object`, `s3_compatible` |
| `src/server/app/__init__.py` | `setup` |
| `src/server/database/api_keys.py` | `get_owner_api_keys` |
| `src/server/services/llm/config.py` | `resolve_byok_llm_client` |

`src/utils/storage/__init__.py` is the sharpest example of why this check
matters: upstream restructured the object-storage API, and the local document
and education services still import the older surface.

## Precedence inside a batch

- User/auth/household/education paths: **local wins**, port only the upstream
  improvements that are provably independent of the local product behaviour.
- Everything else: **upstream wins**. A file the local branch only carries an
  older copy of should end up byte-identical to `origin/main`.
- The financial modules stay in place for this pass. Upstream's core imports
  them (`flash/agent.py` imports `src/tools.market_data.tool` and
  `src/tools.sec.tool`, `market_watch` middleware, prompt templates), so
  excluding them here would re-create a fork in ~20 files. Removing them stays
  a later, dependency-ordered pass.

## Batches

| batch | scope | gate |
|---|---|---|
| 1 | `ptc_agent/agent/middleware/**`, `ptc_agent/core/**`, `llms/**`, `utils/**`, `tools/web/**`, `server/services/{mcp_oauth,egress,plugins,user_skills,vault*}` | `unit/{config,core,llms,middleware,tools,utils}`, import smoke |
| 2 | `server/app/**`, `server/handlers/chat/**`, `server/database/**`, `server/models/**` (minus KEEP/HAND-MERGE) | route-set diff, `unit/server` |
| 3 | the interleaved core: `workspace_manager.py`, `llm/config.py`, `agent/agent.py`, `graph.py`, `flash/**`, `sandbox/{assets,ptc_sandbox,session}.py`, `app/setup.py`, `models/user.py`, `database/{user,workspace}.py`, `threads/messaging.py` | `unit/server`, `unit/ptc_agent`, live smoke |
| 4 | `server/services/persistence/*` plus the `workspace_file_blobs` migration (the deferred 056, renumbered) | migration upgrade/downgrade on the isolated DB |

## Gates that run after every batch

- `git diff origin/main -- <batch paths>` must shrink towards zero.
- The static checkers (call-site kwargs, signature drift, positional overflow,
  route-set diff) must report no new findings — they are what caught the
  `extra_commands` class of drift.
- Focused unit suites for the batch's area, run in the foreground.
- One atomic commit per batch, with the numbers recorded in the runbook.
