# Agent Homework Tool and Contract Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** ship one agent-facing tool (`get_homework_schedule`) and its chat
component, with the backend-to-frontend payload contract **generated** from
Pydantic instead of kept in sync by hand.

**Architecture:** `src/server/app/education/models.py` (already exists) plus a
new artifact-envelope model are the single source of truth. A script exports
their JSON Schema into `web/src/contracts/`, where the frontend turns it into a
zod validator with `z.fromJSONSchema`. One Python test regenerates and compares,
so drift fails the suite. The tool calls the existing `get_task_calendar`
service and returns `(content, artifact)`; the chat card is a props-driven copy
of the dashboard widget that renders the artifact without fetching anything.

**Tech Stack:** Python 3.13+, Pydantic v2, LangChain tools, pytest, uv; React 19,
TypeScript, zod 4.3.6 (`z.fromJSONSchema` — already a dependency), vitest, pnpm.

**Design doc:** `docs/plans/2026-09-12-agent-artifact-contract-design.md`.
The spike results (why `format` is stripped, why there is no union to solve) are
recorded there; do not re-litigate them.

**Branch:** `feature/platform-core-migration` at
`/Users/seanlee/.config/superpowers/worktrees/langalpha/platform-core-migration`.

**Rules for every task:**

- One task = one commit, with the verification output quoted in the message.
- Update `CHANGELOG.md` (Chinese) in the same commit.
- Never overwrite or delete a path in `docs/plans/core-merge-keep-list.txt`.
- Tests must be seen to fail before the implementation that makes them pass.
- Backend: `uv run pytest tests/unit -q -p no:randomly`; `uv run ruff check`.
  Frontend: `cd web && pnpm vitest run`, `pnpm typecheck`, `pnpm lint`.
- Fixtures for anything crossing the wire must come from the **serialisation
  path** (`model_dump(mode="json")`), never from `str()` or
  `json.dumps(default=str)` — see the spike note in the design doc.

---

## Task 1: Export the calendar schema and guard it against drift

This is the task that creates the contract. Everything after it consumes the
generated file.

**Files:**

- Create: `scripts/contracts/export_schemas.py`
- Create: `web/src/contracts/education-calendar.schema.json` (generated, committed)
- Create: `tests/unit/contracts/__init__.py`
- Test: `tests/unit/contracts/test_generated_schemas_are_current.py`

**Step 1: Write the failing test**

```python
"""The committed JSON Schema must be exactly what the exporter produces.

This is the only place drift can happen: the frontend consumes the committed
file, so it cannot diverge structurally. Regenerate with:
    uv run python scripts/contracts/export_schemas.py
"""

import json

from scripts.contracts.export_schemas import OUTPUTS, build_schemas

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_committed_schemas_match_generated():
    for relative_path, schema in build_schemas().items():
        on_disk = json.loads((REPO_ROOT / relative_path).read_text())
        assert on_disk == schema, (
            f"{relative_path} is stale — re-run scripts/contracts/export_schemas.py"
        )


def test_every_declared_output_is_covered():
    # Catches adding a schema to OUTPUTS and forgetting to emit it.
    assert set(build_schemas()) == set(OUTPUTS)
```

**Step 2: Run it and watch it fail**

```bash
uv run pytest tests/unit/contracts/test_generated_schemas_are_current.py -q -p no:randomly
```

Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.contracts'`.

**Step 3: Write the exporter**

`scripts/contracts/export_schemas.py`, using the same `sys.path` prelude the
other scripts under `scripts/` use:

```python
"""Export Pydantic models as JSON Schema for the frontend contract layer.

The Pydantic model is the single source of truth; this emits the wire shape the
frontend validates against. Run it whenever a model in OUTPUTS changes — the
test in tests/unit/contracts fails until you do.

`format` is stripped deliberately. zod's `date-time` validator generated from
JSON Schema only accepts a `Z` suffix, so a real value such as
`2026-09-13T19:00:00+09:00` is rejected even though it is valid ISO 8601. We
want the structural contract (types, required, arrays, nullability), not zod
re-deciding date semantics — the frontend already handles date strings.
"""

OUTPUTS = {
    "web/src/contracts/education-calendar.schema.json":
        EducationTaskCalendarResponse,
}


def _strip_format(node):
    """Recursively drop every `format` keyword so zod does not re-validate dates."""


def build_schemas() -> dict[str, dict]:
    return {
        path: _strip_format(model.model_json_schema())
        for path, model in OUTPUTS.items()
    }


def main() -> None:
    """Write each schema deterministically: sorted keys, 2-space indent, trailing newline."""
```

Deterministic output matters: `json.dumps(schema, indent=2, sort_keys=True)`
plus a trailing newline keeps the diff reviewable and stops the drift test from
failing on key order alone.

**Step 4: Generate and re-run**

```bash
uv run python scripts/contracts/export_schemas.py
uv run pytest tests/unit/contracts -q -p no:randomly
```

Expected: PASS, 2 tests. Sanity-check the committed file by eye: it should have
`$defs` with the three nested models and **no** `"format"` anywhere.

**Step 5: Prove the guard works**

Hand-edit one number in the committed JSON, re-run the test, confirm it fails
naming the file, regenerate, confirm it passes. Quote that in the commit message.

**Step 6: Commit**

```bash
git add scripts/contracts web/src/contracts tests/unit/contracts CHANGELOG.md
git commit -m "feat(contracts): generate the education calendar schema from Pydantic"
```

---

## Task 2: Build the frontend validator from the generated schema

**Files:**

- Create: `web/src/contracts/educationCalendar.ts`
- Create: `web/src/contracts/__tests__/__fixtures__/education-calendar.wire.json`
- Test: `web/src/contracts/__tests__/educationCalendar.test.ts`

**Step 1: Capture a real wire fixture**

The fixture must be produced the way FastAPI serialises a `response_model`:
`EducationTaskCalendarResponse.model_validate(payload).model_dump(mode="json")`,
built from the local database through the existing service. Write it to
`web/src/contracts/__tests__/__fixtures__/education-calendar.wire.json`.
Do **not** hand-write it, and do not build it with `json.dumps(default=str)`.

**Step 2: Write the failing test**

Cover:

1. The real wire fixture parses successfully.
2. A missing required field (`stats`) fails.
3. A wrong type (`is_overdue: "yes"`) fails, and the issue path points at the
   offending task.
4. An unknown extra key is **accepted** — the contract is a boundary check, not
   a strict gate, so a backend that adds a field does not break an older client.
5. The nested task type is reachable and usable on its own (parse a single task
   from the fixture with it).

**Step 3: Run it and watch it fail**

```bash
cd web && pnpm vitest run src/contracts
```

Expected: FAIL — cannot resolve `../educationCalendar`.

**Step 4: Implement**

```ts
// web/src/contracts/educationCalendar.ts
import { z } from 'zod';
import schema from './education-calendar.schema.json';

/**
 * GENERATED CONTRACT — do not edit `education-calendar.schema.json` by hand.
 * It is exported from `src/server/app/education/models.py` by
 * `scripts/contracts/export_schemas.py`, and
 * `tests/unit/contracts/test_generated_schemas_are_current.py` fails once the
 * committed file goes stale.
 */
export const educationTaskCalendarSchema = z.fromJSONSchema(schema);
export type EducationTaskCalendar = z.infer<typeof educationTaskCalendarSchema>;
```

Then expose the nested shapes as named exports so callers do not have to reach
through the parent. **Verify which accessor works and pin it with a test** —
`z.fromJSONSchema` is not documented to preserve `.shape`/`.element`:

1. Preferred: derive from the parent,
   `educationTaskCalendarSchema.shape.days.element.shape.tasks.element`.
2. Fallback: convert the `$defs` entry directly with
   `z.fromJSONSchema({ $ref: '#/$defs/EducationCalendarTaskResponse', $defs: schema.$defs })`.

Whichever works, Step 2 case 5 is what keeps it honest.

**Step 5: Run and commit**

```bash
cd web && pnpm vitest run src/contracts && pnpm typecheck
```

```bash
git add web/src/contracts CHANGELOG.md
git commit -m "feat(web): validate the education calendar payload from the generated schema"
```

---

## Task 3: Point the existing calendar types at the contract

Scope decision: replace **only** the calendar subset of
`web/src/pages/Education/types.ts`. The rest of that file (tasks, textbooks,
learning) stays hand-written for now.

**Files:**

- Modify: `web/src/pages/Education/types.ts`
- Modify: `web/src/pages/Dashboard/widgets/definitions/HomeworkCalendarWidget.tsx`
  (import path only)
- Modify: `web/src/pages/Dashboard/widgets/definitions/__tests__/HomeworkCalendarWidget.test.tsx`
  (fixture types, if the compiler asks)

**Step 1: Delete the duplicated declarations**

Remove `EducationCalendarTask`, `EducationTaskCalendarDay` and
`EducationTaskCalendar`, and re-export from the contract module instead:

```ts
export type {
  EducationTaskCalendar,
  EducationCalendarTask,
  EducationCalendarDay,
} from '@/contracts/educationCalendar';
```

Keep `EducationTaskCalendarRequest` hand-written: it is a *request* shape the
frontend builds, and the exporter only covers responses.

**Step 2: Verify nothing broke**

```bash
cd web && pnpm typecheck && pnpm vitest run src/pages/Education src/pages/Dashboard
```

Expected: PASS with no test changes needed. If a test does need changing, stop
and check whether the generated type is genuinely narrower than the hand-written
one — that difference is information, not friction.

**Step 3: Commit**

```bash
git add web/src/pages/Education/types.ts web/src/pages/Dashboard CHANGELOG.md
git commit -m "refactor(web): derive the education calendar types from the contract"
```

---

## Task 4: Add the artifact envelope and tool argument models

**Files:**

- Create: `src/tools/homework/__init__.py`
- Create: `src/tools/homework/schemas.py`
- Modify: `scripts/contracts/export_schemas.py` (add the envelope to `OUTPUTS`)
- Test: `tests/unit/tools/homework/test_schemas.py`

**Step 1: Write the failing test**

```python
def test_homework_artifact_schema_is_exported():
    schema = build_schemas()["web/src/contracts/homework-schedule.schema.json"]
    assert schema["properties"]["type"]["const"] == "homework_schedule"
    assert "student_names" in schema["properties"]


def test_artifact_round_trips():
    artifact = HomeworkScheduleArtifact(
        window="2w",
        start_date=date(2026, 9, 12),
        end_date=date(2026, 9, 25),
        timezone="Asia/Tokyo",
        stats=EducationCalendarStatsResponse(
            today_count=0, week_count=0, overdue_count=0, completed_count=0
        ),
        days=[],
        student_names={},
    )
    assert HomeworkScheduleArtifact.model_validate(
        artifact.model_dump(mode="json")
    ).type == "homework_schedule"
```

**Step 2: Run it and watch it fail**

```bash
uv run pytest tests/unit/tools/homework -q -p no:randomly
```

**Step 3: Implement `src/tools/homework/schemas.py`**

Exactly the models from the design doc: `HomeworkScheduleArgs` and
`HomeworkScheduleArtifact`. The artifact reuses `EducationCalendarDayResponse`
and `EducationCalendarStatsResponse` rather than re-declaring them — that reuse
is what makes the envelope and the dashboard widget structurally the same
payload.

`HomeworkScheduleArgs` validators:

- `start_date` and `end_date` must be supplied together.
- `end_date >= start_date`.
- The span must be under 62 days, mirroring the calendar API's ceiling so the
  model gets a clear message instead of a downstream 400.

**Step 4: Regenerate and commit**

```bash
uv run python scripts/contracts/export_schemas.py
uv run pytest tests/unit/contracts tests/unit/tools/homework -q -p no:randomly
```

```bash
git add src/tools/homework scripts/contracts web/src/contracts CHANGELOG.md
git commit -m "feat(homework): define the artifact envelope and tool arguments"
```

---

## Task 5: The tool

**Files:**

- Create: `src/tools/homework/tools.py`
- Test: `tests/unit/tools/homework/test_get_homework_schedule.py`

**Step 1: Write the failing test**

Use the existing education test fixtures for a household with tasks. Cover:

1. `window="today"` resolves to a single day in the household's timezone.
2. `window="last_week"` resolves to the previous Monday–Sunday, matching the
   backend's `isoweekday` week definition — assert the exact dates.
3. `window="this_week"` resolves to Monday–Sunday of the current week.
4. Explicit `start_date`/`end_date` are used verbatim and win over `window`.
5. `start_date` without `end_date` (and the reverse) is a validation error.
6. A span over 62 days is a validation error with a readable message.
7. The artifact validates against `HomeworkScheduleArtifact` — round-trip it.
8. A **different household's** tasks never appear.
9. A student account sees only its own tasks.
10. `student_names` maps every `assigned_student_id` present in `days`.
11. `content` mentions the count and the range, and is capped: build a payload
    with more tasks than the cap and assert the tail says how many were omitted.

**Step 2: Run it and watch it fail**

```bash
uv run pytest tests/unit/tools/homework -q -p no:randomly
```

**Step 3: Implement**

```python
@tool(
    "get_homework_schedule",
    args_schema=HomeworkScheduleArgs,
    response_format="content_and_artifact",
)
async def get_homework_schedule(...):
    """Look up this household's homework for a period.

    Use this whenever the user asks what homework is due — today, this week,
    next week, last week, or an explicit date range.
    """
```

- `user_id` from `config.configurable` (`src/tools/automation/tools.py:33` is
  the pattern to copy).
- Resolve `window` to `(start_date, end_date)` in the household timezone.
- Call the existing `get_task_calendar(user_id=..., start_date=..., end_date=...)`.
- Resolve child names from the membership context so the artifact is
  self-contained.
- Feed the canonical `EducationTaskCalendarResponse.model_dump(mode="json")`
  shape into the artifact, so what we validate is what the API would send.
- Build `content` as a compact markdown digest, capped.

**Step 4: Run and commit**

```bash
uv run pytest tests/unit/tools/homework -q -p no:randomly
uv run ruff check src/tools/homework tests/unit/tools/homework
```

```bash
git add src/tools/homework tests/unit/tools CHANGELOG.md
git commit -m "feat(homework): add the get_homework_schedule tool"
```

---

## Task 6: Expose the tool to PTC

**Files:**

- Modify: `src/ptc_agent/agent/agent.py` (tool assembly, around line 660)
- Test: whichever suite already asserts the PTC tool list

**Step 1: Write the failing test** — the tool is present for an ordinary
account and **absent** for a managed teaching job (`managed_policy is not None`),
mirroring how the finance tools are gated.

**Step 2: Run it and watch it fail.**

**Step 3: Register it** next to the other domain tools behind the same guard:

```python
if managed_policy is None:
    tools.append(get_homework_schedule)
```

**Step 4: Run the suite and commit.**

---

## Task 7: Expose the tool to Flash

**Files:**

- Modify: `src/ptc_agent/agent/flash/agent.py` (`_build_tools` and the module docstring)
- Test: the Flash tool-list suite

**Step 1: Write the failing test** — `get_homework_schedule` is in Flash's tool
list.

**Step 2: Register it** in `_build_tools`.

**Step 3: Update the module docstring in the same commit.** It currently says
"External tools only (no sandbox, no MCP)". That sentence becomes false the
moment this lands, and a stale comment is worse than none. Replace it with the
actual rule: external tools plus first-party household reads, still no sandbox
and no MCP.

**Step 4: Run the suite and commit.**

---

## Task 8: The chat card

**Files:**

- Create: `web/src/pages/ChatAgent/components/charts/InlineHomeworkCard.tsx`
- Create: `web/src/pages/ChatAgent/components/charts/__tests__/__fixtures__/homework-artifact.json`
- Test: `web/src/pages/ChatAgent/components/charts/__tests__/InlineHomeworkCard.test.tsx`

**Step 1: Copy, then strip**

Start from `web/src/pages/Dashboard/widgets/definitions/HomeworkCalendarWidget.tsx`
and keep: the bucket definitions and `BUCKET_ORDER`, `bucketFor`, `dueClock`,
`dayDots`, the task row, the stats strip, and the `SubjectIcon` usage. Reuse the
existing `dashboard.widgets.homeworkCalendar.*` locale keys unless a string is
genuinely new.

Remove everything container-shaped: `useEducationTaskCalendar`,
`useEducationMembers`, `useAuth`, `updateConfig`, `useWidgetContextExport`,
`RowAttachButton`, `useNavigate`, and the range/view controls that exist to write
prefs. Props are `{ artifact: Record<string, unknown>; onClick?: () => void }` to
match `INLINE_ARTIFACT_MAP`; validate inside with the generated zod schema and
fall back to a small "unavailable" state when validation fails.

**Step 2: Write the failing test**

1. Renders the stats strip and the buckets from a fixture artifact.
2. Child names come from `student_names` — **and no network call is made**.
   Prove it by rendering without any `QueryClientProvider`; a hook that fetched
   would throw.
3. An overdue task is marked.
4. An unknown `subject_code` falls back to the default icon rather than crashing.
5. A payload that fails the schema renders the fallback state instead of
   throwing — this is the payoff of having a schema at all.
6. An extra unknown key in the payload is ignored (older client, newer backend).

**Step 3: Run it and watch it fail, implement, re-run.**

**Step 4: Commit.**

---

## Task 9: Register the card and verify replay

**Files:**

- Modify: `web/src/pages/ChatAgent/components/charts/InlineArtifactCards.tsx`
- Test: the suite covering `INLINE_ARTIFACT_TOOLS` / `INLINE_ARTIFACT_MAP`

**Step 1: Register** — add `get_homework_schedule` to `INLINE_ARTIFACT_TOOLS`
and `homework_schedule: InlineHomeworkCard` to `INLINE_ARTIFACT_MAP`.

**Step 2: Write the failing test** — the map has the entry and the tool name is
in the inline set. This mapping is pure string convention today, which is
exactly why the assertion is worth having.

**Step 3: Verify replay explicitly — this is a blocker, not a follow-up.**

Ask the tool in a real thread, then reload the thread. The card must render from
stored history. If the artifact does not survive into the history projection,
stop and report: the design assumes it does, and the answer changes whether the
card can rely on the payload or must re-derive it. Record the outcome in the
commit message either way.

**Step 4: Commit.**

---

## Task 10: End-to-end verification and close-out

**Step 1: Real browser, real data.** With the backend on 18000 and the frontend
on 5177 (Postgres 15432), ask "最近我有哪些作业要做" and confirm the card renders
the seeded household schedule. Verify in both a Flash thread and a PTC thread,
since both now carry the tool.

**Step 2: Range variants.** Ask "今天有什么作业" and "上周的作业" and confirm each
returns the right window.

**Step 3: Full suites.**

```bash
uv run pytest tests/unit -q -p no:randomly
uv run ruff check src/ migrations/ scripts/ops/ scripts/contracts/
```

```bash
cd web && pnpm vitest run && pnpm typecheck && pnpm lint && pnpm build
```

Baselines to hold: backend 7547 passed / 1 xfailed and growing; frontend 248
files / 2419 tests and growing; lint 0 errors / 56 warnings; critical path under
450 kB gz.

**Step 4: Write the mechanism up.** Add a short section to the design doc
recording what a future tool author must do, in order: add the Pydantic model,
run the exporter, consume the generated zod type, register the artifact type —
and the tests that fail if a step is skipped. The pilot's value is the recipe,
not the homework card.

**Step 5: Commit.**

---

## Deliberately not in this plan

- A global artifact registry or a discriminated union across artifact types.
  This plan proves the *per-artifact* contract; the union is its own design.
- Backfilling `type` onto artifacts that lack one, or migrating the ~20 existing
  untyped read sites.
- Extracting the dashboard widget's view layer into shared components. The chat
  card is a deliberate copy; only the locale keys and `SubjectIcon` are shared.
