# Resume here — state of the merge at context compaction

Everything below is on disk; nothing depends on the chat history.

## Where we are

- Branch `feature/platform-core-migration`, worktree
  `/Users/seanlee/.config/superpowers/worktrees/langalpha/platform-core-migration`.
- Rollback point: `git reset --hard checkpoint/pre-core-merge`.
- Merge applied: the TAKE set (284 `src` files + 485 test files) from
  `origin/main`, plus the first hand-merges. Serviceable but not finished.
- Recent commits, newest first:
  `b4401350` docs for task 1 · `0173d1ca` task 1 done · `04af068b` task 1
  partial · `9c3bca65` the plan · `da954580` household billing provenance +
  first post-merge fixes · `df740f00` the TAKE merge.

## The plan

`docs/plans/2026-09-10-post-merge-completion.md` — eight tasks, each with files,
reproduction command, change, verification command and commit message. It
carries a per-task **Status** line; read that first.

- Task 1 (managed-textbook hooks) — **DONE**.
- Task 2 (household LLM re-home) — **IN PROGRESS**; the plan file has the exact
  next steps (take the three upstream llm files, early-return into the household
  resolver inside `resolve_llm_config`, re-point importers, test, commit).
- Tasks 3–8 — not started.

## Facts worth not rediscovering

- Classification lists live beside the plan:
  `core-merge-keep-list.txt` (78 local-only files — never overwrite),
  `core-merge-hand-merge.txt`, `core-merge-take-origin.txt`.
- Household billing decision (user-approved, plan A): the **owner pays**; the
  credit gate is given `model_owner_user_id` from
  `config.llm_runtime_metadata`; `billing_type` stays one of
  `platform/byok/oauth` (household stamps `byok`), and the household facts ride
  in `credential_source="household"` plus the id fields.
- The finance stack is **identical to upstream** (commit `ac4cfe2d` restored it),
  so there is no local finance divergence left in `src/`.
- Host toolchain: backend `18000`, frontend `15177`; isolated infra on
  `15432/16379/19000`; the Clash Verge profile is on real-IP DNS with TUN, which
  is what makes host-side egress work at all.
- `tests/unit/{config,core,llms,utils}` 1490 passed; `tests/unit/ptc_agent`
  763 passed; `middleware` and `server` suites are still to be driven green.
- Deferred by decision: the workspace-file blob persistence (`056`, renumber to
  `058`) and the PTC + Docker-sandbox end-to-end check (tasks 6 and 7).
