# Natural Language Homework Tool Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Let authenticated parents create text-only household homework from any PTC or Flash conversation through one shared native tool and a default Skill.

**Architecture:** Add a host-side LangChain tool under `src/tools/education` that reads the caller identity from `RunnableConfig`, resolves a unique student within the caller's household, normalizes the structured assignment fields, and delegates all authorization and persistence to `src.server.services.education_tasks.create_task`. Register that same tool in both agent factories and expose a guidance-only `family-homework` Skill to both modes; the Skill handles intent recognition and clarification while the tool remains the security boundary. Attachments, MinIO, and chat-upload mapping are explicitly outside this phase.

**Tech Stack:** Python 3.13, LangChain `@tool`, async psycopg database helpers, Pydantic/LangChain tool schemas, project-native Skills middleware, pytest/pytest-asyncio, Ruff.

---

### Task 1: Add household student resolution and tool contract tests

**Files:**
- Create: `tests/unit/tools/test_education_homework.py`
- Modify: `src/server/database/education_members.py`

**Step 1: Write the failing tests**

Add focused async tests for a database helper that lists only student members in a household, preserving `user_id`, `display_name`, and `grade_code`. Add tool-level tests that assert:

- missing `configurable.user_id` returns a readable caller-identity error;
- a non-parent caller is rejected before task creation;
- a unique student display name resolves to that student's user ID;
- an unknown or ambiguous name returns a clarification error and does not call `create_task`;
- a student name from another household is never accepted.

Patch only the database/service boundaries in these unit tests; do not bypass the tool's own argument normalization.

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/tools/test_education_homework.py -q`

Expected: FAIL because the student-list helper and education tool do not exist.

**Step 3: Implement the minimal database helper**

Add `list_student_membership_context(household_id)` to `src/server/database/education_members.py`. Query `education_memberships` joined to `education_student_profiles`, filter `role = 'student'`, and return dictionaries ordered by creation time. Keep the helper read-only and household-scoped.

**Step 4: Run the focused tests**

Run: `uv run pytest tests/unit/tools/test_education_homework.py -q`

Expected: The database-helper test passes; tool tests still fail because the tool is not implemented.

**Step 5: Commit**

```bash
git add src/server/database/education_members.py tests/unit/tools/test_education_homework.py
git commit -m "test: define household homework tool boundary"
```

### Task 2: Implement the text homework native tool

**Files:**
- Create: `src/tools/education/__init__.py`
- Create: `src/tools/education/homework.py`
- Modify: `tests/unit/tools/test_education_homework.py`

**Step 1: Extend the failing tests**

Cover the public tool contract `education_create_homework` with tests for:

- required fields: student name, title, description, ISO `due_at`, subject/type, frequency;
- optional weekly weekdays and practice source;
- ISO timestamp parsing requiring a timezone offset;
- invalid frequency/weekday/practice-source combinations being returned as tool errors;
- a complete parent request calling `create_task` with the resolved student ID, household timezone, empty `material_asset_ids`, and no attachment fields;
- a stable idempotency key derived from the current run/request identity plus canonical text assignment fields, so a retry of the same tool call is safe while two intentionally distinct calls can coexist;
- a successful result containing the created task ID, student name, local due time, and a `/education` destination without claiming attachment support.

Use real schema validation and a small fake service boundary; do not test implementation-private helper details.

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/tools/test_education_homework.py -q`

Expected: FAIL because `src.tools.education.homework` and `education_create_homework` do not exist.

**Step 3: Implement the minimal tool**

In `src/tools/education/homework.py`:

- Extract `user_id` and optional `timezone`/`run_id` from `RunnableConfig.configurable` (and metadata only where the existing LangGraph config places it), rejecting absent identity.
- Load the caller membership with `get_membership_for_user`; require `role == 'parent'` and use its `household_id`/timezone.
- Load household students with `list_student_membership_context`; compare normalized display names. Return a targeted “student required/not found/ambiguous” message with available names only for the caller's household.
- Accept stable dictionary codes (`subject_code`, `type_code`, optional `practice_source_code`) and delegate validation to `education_tasks.create_task` rather than duplicating dictionary rules.
- Parse `due_at` with `datetime.fromisoformat`, require an offset, and pass it through unchanged so the service converts it to the household timezone. Validate `weekdays` only for `weekly` and pass an empty material asset list because this phase is text-only.
- Build a deterministic, bounded idempotency key from a canonical JSON payload plus the current run/request identity; never accept `parent_user_id` or `household_id` as tool arguments.
- Catch `EducationTaskError` subclasses and return concise, model-readable error text. Return structured `content_and_artifact` output only after persistence succeeds.

Export the tool from `src/tools/education/__init__.py`. Keep the module host-side and independent of sandbox filesystem or MinIO code.

**Step 4: Run focused tests and lint**

Run: `uv run pytest tests/unit/tools/test_education_homework.py -q`

Expected: PASS.

Run: `uv run ruff check src/tools/education src/server/database/education_members.py tests/unit/tools/test_education_homework.py`

Expected: PASS with no diagnostics.

**Step 5: Commit**

```bash
git add src/tools/education tests/unit/tools/test_education_homework.py
git commit -m "feat: add text homework creation tool"
```

### Task 3: Register the tool in PTC and Flash

**Files:**
- Modify: `src/ptc_agent/agent/agent.py`
- Modify: `src/ptc_agent/agent/flash/agent.py`
- Modify: `tests/unit/ptc_agent/agent/test_education_homework_registration.py`

**Step 1: Write the failing registration tests**

Add tests that exercise each factory's tool-building path with lightweight stubs and assert exactly one `education_create_homework` tool is present in PTC and Flash. Assert the same tool object/function contract is used in both modes and that no MCP/Vault registration is added.

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/ptc_agent/agent/test_education_homework_registration.py -q`

Expected: FAIL because neither factory registers the education tool.

**Step 3: Register the shared native tool**

Import `education_create_homework` from `src.tools.education` and append it to the ordinary `tools` list in `PTCAgent.create_agent` for non-managed parent chat builds, and to `FlashAgent._build_tools`. Keep the managed textbook policy path unchanged so service-owned workers do not gain household operations. Do not add it to MCP summaries or workspace-configurable MCP servers.

**Step 4: Run registration and existing factory tests**

Run: `uv run pytest tests/unit/ptc_agent/agent/test_education_homework_registration.py tests/unit/middleware/skills/test_skill_registry.py -q`

Expected: PASS.

**Step 5: Commit**

```bash
git add src/ptc_agent/agent/agent.py src/ptc_agent/agent/flash/agent.py tests/unit/ptc_agent/agent/test_education_homework_registration.py
git commit -m "feat: expose homework tool in ptc and flash"
```

### Task 4: Add and register the default family-homework Skill

**Files:**
- Create: `skills/family-homework/SKILL.md`
- Modify: `src/ptc_agent/agent/middleware/skills/registry.py`
- Create: `tests/unit/middleware/skills/test_family_homework_skill.py`

**Step 1: Write the failing Skill tests**

Assert that `family-homework` has valid frontmatter, is exposed in both PTC and Flash, points to `skills/family-homework/SKILL.md`, and describes the exact tool name. Assert the body instructs the model to:

- recognize explicit homework-assignment intent;
- map Chinese subject/type/source phrases to dictionary codes only when unambiguous;
- ask only for missing or ambiguous student, due time, subject/type, or practice source;
- use the caller's local/family timezone for relative times;
- call `education_create_homework` and never claim success from prose alone;
- state that the first phase accepts text only and does not upload or attach files.

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/middleware/skills/test_family_homework_skill.py -q`

Expected: FAIL because the registry entry and Skill file do not exist.

**Step 3: Implement the Skill and registry entry**

Add a concise `SKILL.md` with YAML frontmatter whose description exactly matches the `SkillDefinition`. Register `family-homework` with `tools=[education_create_homework]`, `exposure="both"`, and its Skill path. Keep the Skill guidance-only: validation, authorization, timezone conversion, and writes remain in the native tool/service.

**Step 4: Run Skill tests**

Run: `uv run pytest tests/unit/middleware/skills/test_family_homework_skill.py tests/unit/middleware/skills/test_skill_registry.py -q`

Expected: PASS.

**Step 5: Commit**

```bash
git add skills/family-homework src/ptc_agent/agent/middleware/skills/registry.py tests/unit/middleware/skills/test_family_homework_skill.py
git commit -m "feat: add family homework skill"
```

### Task 5: Verify end-to-end boundaries and document the release

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `tests/unit/tools/test_education_homework.py`

**Step 1: Add regression cases**

Add tests for no grade, invalid subject/type mapping, invalid practice source, weekly initial-date mismatch, service permission errors, and idempotent retry. Assert no database write is attempted on every rejected case. Include a student caller test that constructs valid-looking arguments but receives the parent-only rejection.

**Step 2: Run the required verification**

Run:

```bash
uv run pytest tests/unit/tools/test_education_homework.py tests/unit/ptc_agent/agent/test_education_homework_registration.py tests/unit/middleware/skills/test_family_homework_skill.py -q
uv run pytest tests/unit/middleware/skills tests/unit/server/services/test_education_tasks.py -q
uv run ruff check src tests/unit/tools/test_education_homework.py tests/unit/ptc_agent/agent/test_education_homework_registration.py tests/unit/middleware/skills/test_family_homework_skill.py
```

Expected: all focused and affected tests pass and Ruff reports no diagnostics. If an existing test path differs, locate the nearest education-task unit test and record the exact substitute in the commit notes.

**Step 3: Update the Chinese changelog**

Add a concise entry describing native text homework creation from PTC/Flash, parent-only enforcement, shared household students, and the explicit first-phase no-attachment boundary. Do not mention credentials or local database data.

**Step 4: Commit the verified release note**

```bash
git add CHANGELOG.md tests/unit/tools/test_education_homework.py
git commit -m "test: verify natural language homework boundaries"
```

**Step 5: Manual smoke check**

With the normal local services running, send a parent Flash message such as “给 Henry 布置数学练习，明天晚上八点完成，校外作业：完成第 3 页练习” and confirm the model calls the tool, the task appears under `/education`, and a repeated transport retry does not create a duplicate. Then send the same request from a student account and confirm a clear permission error without a task row.

