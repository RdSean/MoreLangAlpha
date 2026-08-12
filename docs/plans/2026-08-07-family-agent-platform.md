# Family Agent Platform Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Convert LangAlpha into a general Agent platform and add a first-party family education module with local accounts, homework management, MinIO attachments, and role-safe Agent sessions.

**Architecture:** First remove the finance runtime slice while preserving PTC, Flash, workspaces, sandbox execution, Skills, MCP code generation, SSE, background subagents, and PostgreSQL persistence. Then add first-party authentication and an `education_` domain behind FastAPI-only APIs. The React application owns all education UI and uses existing LangAlpha design tokens, primitives, React Query, raw SSE conventions, and navigation patterns; no Family Learning Hub UI, Supabase client, LiteLLM assistant service, e-book, question bank, paper, or image-review code is imported.

**Tech Stack:** Python 3.13+, FastAPI, psycopg3, Alembic raw SQL, PostgreSQL, Redis, MinIO through the existing boto3 S3-compatible adapter, React 19, Vite, TypeScript, Tailwind, Radix, React Query, Vitest, Playwright.

---

## Scope Guardrails

- Keep PTC and Flash. Student accounts are Flash-only; they cannot create PTC workspaces, use sandbox execution, MCP, Vault, custom skills, or automations.
- Remove financial tools, providers, MCP servers, data protocol packages, price triggers, market routes, MarketView, TradingView, financial dashboard widgets, finance Skills, and finance-specific prompts/configuration.
- Keep plain-text parent feedback. Do not implement image markup, Konva, review-image artifacts, e-books, question banks, paper composition, library, or the legacy family AI assistant.
- All browser data access goes through the LangAlpha FastAPI server. Do not add a direct PostgreSQL or Supabase browser client.
- Do not access MinIO until attachment tests require it. When used, follow `AGENTS.md`: use the configured instance, only a validated `education/` object prefix, no bucket-wide mutation, and never expose credentials.
- After verified substantial changes, add a Chinese `CHANGELOG.md` entry and make an atomic commit containing only the feature's files.

## Task 1: Establish the general Agent runtime boundary

**Files:**
- Modify: `src/ptc_agent/agent/agent.py`
- Modify: `src/ptc_agent/agent/flash/agent.py`
- Modify: `src/ptc_agent/core/sandbox/_shared.py`
- Modify: `agent_config.yaml`
- Create: `tests/unit/ptc_agent/agent/test_generic_tool_boundary.py`
- Create: `tests/unit/ptc_agent/core/sandbox/test_generic_sandbox_packages.py`

**Step 1: Write failing boundary tests.**

Assert that the default PTC and Flash factories expose only generic tools and that sandbox bootstrap does not upload `data_client` or `market_protocol`.

**Step 2: Run focused tests to verify RED.**

Run: `uv run pytest tests/unit/ptc_agent/agent/test_generic_tool_boundary.py tests/unit/ptc_agent/core/sandbox/test_generic_sandbox_packages.py -q`

Expected: FAIL because the current factories import SEC/market tools and the sandbox package tuple names financial packages.

**Step 3: Implement the generic boundary.**

Remove direct market/SEC imports and registrations from PTC and Flash. Keep Web search/fetch, filesystem, code execution, widgets, Todo, and Secretary according to their existing mode restrictions. Remove built-in financial MCP entries and the finance package upload tuple; retain custom workspace MCP support.

**Step 4: Verify GREEN.**

Run the focused tests, then `uv run pytest tests/unit/ptc_agent/agent/ tests/unit/ptc_agent/core/sandbox/ -q`.

**Step 5: Record and commit.**

Add a Chinese `CHANGELOG.md` entry describing the general Agent tool boundary, then commit only this task's files.

## Task 2: Remove finance HTTP/runtime registration and neutralize platform configuration

**Files:**
- Modify: `src/server/app/setup.py`
- Modify: `config.yaml`
- Modify: `src/server/services/workspace_manager.py`
- Modify: `migrations/versions/001_initial_schema.py`
- Create: `tests/unit/server/app/test_generic_router_registration.py`
- Create: `tests/unit/server/services/test_generic_startup_services.py`

**Step 1: Write failing tests.**

Assert startup does not import/start the market feed, price monitor, market insight worker, or market WebSocket router; assert the registered API routes exclude market, SEC proxy, watchlist, portfolio, chart annotations, and price trigger endpoints.

**Step 2: Run focused tests to verify RED.**

Run: `uv run pytest tests/unit/server/app/test_generic_router_registration.py tests/unit/server/services/test_generic_startup_services.py -q`

**Step 3: Implement the runtime removal.**

Delete service lifecycle wiring and routers, preserve general scheduler/automation support, remove finance config blocks, and remove market-specific workspace credential injection. Rebuild the migration baseline rather than preserving finance application tables because no production data must survive; retain users, workspaces, threads, runs, automations, vault, MCP, provenance, and LangGraph tables.

**Step 4: Verify GREEN.**

Run focused tests plus `uv run pytest tests/unit/server/app/ tests/unit/server/services/ -q`.

**Step 5: Record and commit.**

Add Chinese release notes and make an atomic commit.

## Task 3: Remove finance frontend and product surface

**Files:**
- Modify: `web/src/components/Main/Main.tsx`
- Modify: `web/src/components/nav/navItems.ts`
- Modify: `web/src/App.tsx`
- Modify: `web/src/pages/Dashboard/*`
- Delete: `web/src/pages/MarketView/`
- Delete: finance-only Dashboard widgets, hooks, API types, and localization keys
- Create: `web/src/components/Main/__tests__/genericRoutes.test.tsx`

**Step 1: Write a failing route/navigation test.**

Assert the navigation and route table expose chat, workspaces, files, automations, settings, and the education entry, but not MarketView or finance pages.

**Step 2: Run RED.**

Run: `cd web && pnpm test -- genericRoutes.test.tsx`

**Step 3: Implement the product-surface removal.**

Replace the finance dashboard with a neutral workspace/activity dashboard. Remove financial imports before deleting files so TypeScript identifies every remaining coupling. Keep shared file viewer, chat, workspace management, and the dashboard grid only where it remains generic.

**Step 4: Verify GREEN.**

Run `cd web && pnpm typecheck && pnpm test -- genericRoutes.test.tsx`.

**Step 5: Record and commit.**

Add Chinese release notes and make an atomic commit.

## Task 4: Build first-party local authentication and family membership

**Files:**
- Modify: `pyproject.toml`, `uv.lock`
- Modify: `src/server/utils/api.py`, `src/server/auth/jwt_bearer.py`
- Create: `src/server/auth/local_sessions.py`
- Create: `src/server/database/auth_accounts.py`
- Create: `src/server/database/education_members.py`
- Create: `src/server/app/auth.py`
- Create: `migrations/versions/025_add_local_auth_and_education_members.py`
- Modify: `src/server/app/setup.py`, `web/src/contexts/AuthContext.tsx`, `web/src/api/client.ts`
- Create: focused backend and frontend authentication tests

**Step 1: Write failing tests.**

Cover parent registration, parent-created child account, password login, opaque HttpOnly session rotation/logout, and endpoint denial for unauthenticated actors. Cover that the existing `CurrentUserId` contract returns the authenticated database user without changing all router signatures.

**Step 2: Run RED.**

Run the focused backend and web auth test files.

**Step 3: Implement local auth.**

Add Argon2id password hashes and hashed opaque sessions in PostgreSQL; use `users.user_id` as the permanent identity. A parent creates a household and child membership; no public child signup. Replace Supabase browser/session handling with cookie-based auth while preserving the existing Axios and raw-SSE request layers.

**Step 4: Verify GREEN.**

Run focused tests, the current auth tests, and migration upgrade/downgrade against an isolated Docker PostgreSQL database.

**Step 5: Record and commit.**

Add Chinese release notes and make an atomic commit.

## Task 5: Add MinIO-backed education assets

**Files:**
- Modify: `docker-compose.yml`, `.env.example`, `agent_config.yaml`
- Create: `deploy/minio/init-education-bucket.sh`
- Create: `src/server/database/education_assets.py`
- Create: `src/server/services/education_assets.py`
- Create: `src/server/app/education/assets.py`
- Create: `tests/unit/server/services/test_education_assets.py`
- Create: provider-Docker integration tests

**Step 1: Write failing tests.**

Cover allowed MIME/size validation, key generation under `education/<household>/<asset>`, failed-upload rollback, access-scoped download URLs, and refusal to issue a URL across household/member boundaries.

**Step 2: Run RED.**

Run: `uv run pytest tests/unit/server/services/test_education_assets.py -q`

**Step 3: Implement the asset service.**

Use the existing S3-compatible adapter configured for MinIO path addressing. A dedicated init container creates the application bucket only when absent; it never deletes or changes existing buckets. The FastAPI upload route proxies the first-release upload, records only private metadata and storage key, and returns no durable signed URLs.

**Step 4: Verify GREEN.**

Run focused unit tests, then isolated Docker MinIO/PostgreSQL integration tests. Do not use the pre-existing remote MinIO until a manual, permission-limited smoke test is explicitly needed.

**Step 5: Record and commit.**

Add Chinese release notes and make an atomic commit.

## Task 6: Implement homework persistence, transitions, and APIs

**Files:**
- Create: `src/server/database/education_tasks.py`
- Create: `src/server/services/education_tasks.py`
- Create: `src/server/app/education/router.py`
- Create: `src/server/app/education/models.py`
- Modify: `src/server/app/setup.py`
- Create: `migrations/versions/026_add_education_tasks.py`
- Create: task service and router unit tests

**Step 1: Write failing tests.**

Cover parent-only task creation/cancellation, student-only submission, idempotent submission, parent text-only review, the full `open -> submitted -> revision_requested -> submitted -> completed` state machine, immutable submission sequence, and history retention when a rule is stopped.

**Step 2: Run RED.**

Run the focused education task test suite.

**Step 3: Implement the education domain.**

Create task rules, materialized instances, task/submission attachments, immutable submissions, and text-only reviews. Materialize recurrence server-side using household timezone and PostgreSQL transaction locks; use unique constraints and `ON CONFLICT DO NOTHING` for multi-worker idempotence. Remove any image-review field and do not create e-book/content tables.

**Step 4: Verify GREEN.**

Run focused tests and an isolated PostgreSQL multi-worker/concurrency test.

**Step 5: Record and commit.**

Add Chinese release notes and make an atomic commit.

## Task 7: Build the education frontend from LangAlpha primitives

**Files:**
- Create: `web/src/pages/Education/`
- Create: `web/src/pages/Education/api.ts`, `queries.ts`, `types.ts`
- Create: `web/src/pages/Education/components/`
- Modify: `web/src/components/Main/Main.tsx`, `web/src/components/nav/navItems.ts`, `web/src/lib/queryKeys.ts`
- Create: co-located Vitest tests and Playwright dual-account tests

**Step 1: Write failing route and interaction tests.**

Cover role-aware landing, parent task creation, student submission, text feedback, resubmission, attachment state, and access denial. Assert the implementation uses current LangAlpha `Button`, `Dialog`, `Input`, `Textarea`, `Tooltip`, tokenized colors, and React Query keys rather than legacy family CSS or Supabase repositories.

**Step 2: Run RED.**

Run targeted Vitest files.

**Step 3: Implement the new UI.**

Build parent and student workspaces using LangAlpha's Quiet Workspace design. Use compact full-width sections, stable status labels, Lucide icons, accessible dialogs, and current responsive navigation. Do not copy `FamilyShell`, legacy classes, assistant pages, or Konva components.

**Step 4: Verify GREEN.**

Run `cd web && pnpm typecheck && pnpm test`, then targeted Playwright coverage.

**Step 5: Record and commit.**

Add Chinese release notes and make an atomic commit.

## Task 8: Wire education accounts to safe Agent sessions and complete release verification

**Files:**
- Modify: workspace creation/authorization routes and services
- Modify: Flash/PTC admission policy and workspace UI guards
- Modify: `CHANGELOG.md`, `README.md`, `docs/README.zh-CN.md`, `AGENTS.md`
- Create: authorization, SSE, and Playwright tests

**Step 1: Write failing policy tests.**

Assert a student receives a private Flash workspace/session but cannot create a PTC workspace, run code, configure MCP/Vault, or schedule automations. Assert parent and child Threads remain private by owner even in the same household.

**Step 2: Run RED.**

Run focused policy tests.

**Step 3: Implement and document the policy.**

Create or resolve each user's learning Flash workspace on demand. Preserve existing thread ownership and SSE contracts; do not make a household-shared sandbox. Update product documentation to describe the generic Agent platform and family education module, removing finance claims.

**Step 4: Verify full release.**

Run backend unit tests, frontend typecheck/tests, isolated PostgreSQL/MinIO integration tests, Playwright parent/student workflow, and a LAN smoke test at `0.0.0.0:5177`. Before any MinIO smoke test, enumerate target settings and verify the education-only prefix without deleting data.

**Step 5: Record and commit.**

Update Chinese changelog and make the final atomic commit.
