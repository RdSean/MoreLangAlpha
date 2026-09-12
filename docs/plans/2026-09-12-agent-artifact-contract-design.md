# Agent Artifact Contract Design

**Status:** proposed 2026-09-12, awaiting review before implementation.

**Goal:** build one agent-facing tool and its chat component end to end, using a
**generated contract** between backend and frontend rather than the current
hand-kept alignment. The subject matter is deliberately small — "what homework
do I have coming up?" — because the point is the *mechanism*, and this makes it
repeatable for every later tool.

## Why this is worth doing as a pilot

The current tool→frontend path has no contract, only a convention. Findings
from reading it (all verified, not inferred):

- Tools return LangChain's `ToolMessage(content, artifact)` pair. 24 tools
  declare `response_format="content_and_artifact"` in their decorator and
  `WebFetch` does it through `StructuredTool.from_function`, so even *finding*
  the set takes more than one pattern.
- The artifact dict is authored freehand per tool, and its shape differs
  between the success and failure paths: success yields
  `{"type": "automations", "mode": "created", ...}`, failure commonly yields
  `{"mcp_trace": []}` with **no `type` at all**. So "every artifact has a
  `type`" is not true today.
- The frontend types it as `artifact?: unknown`, reads it at ~20 sites, and
  every one is an `as Record<string, unknown>` cast followed by dot access.
  Dispatch is string equality on `artifact.type` *and* on the tool name.
- Where a written contract does exist (`src/tools/web/types.py`, "the
  non-negotiable half of the protocol") it lives only in Python and is not
  mirrored.
- The one place a front/back mirror was attempted (`mcpSchemas.ts`) documents
  itself as a hand-kept copy: "Keep the two in sync".

Meanwhile the schema we need **already exists**: `EducationTaskCalendarResponse`
and its three nested models in `src/server/app/education/models.py`. The
frontend re-declares the same shapes by hand in `Education/types.ts`. So this
pilot does not add a layer — it removes an existing duplication and puts a
guard around it.

## The spike (run 2026-09-12, results are the basis for the decisions below)

Generated `EducationTaskCalendarResponse.model_json_schema()` and fed it to
`z.fromJSONSchema` (zod 4.3.6, already a dependency):

| Check | Result |
|---|---|
| `$defs` / `$ref` for nested models | expanded correctly |
| 8 `anyOf` nullable properties | handled |
| real wire payload | **PASS** |
| wrong type on a field (`is_overdue: "yes"`) | rejected |
| unknown keys | accepted (non-strict) |
| `format: "date-time"` with a `Z` suffix | accepted |
| `format: "date-time"` with `+09:00` | **rejected** |
| `oneOf` / `discriminator` in the schema | **0** |

Two conclusions that changed the plan:

1. **There is no discriminated union to solve here.** The 8 `anyOf`s are
   Pydantic's "nullable", not variants. The union question belongs to a future
   global artifact registry, not to this pilot, and it must not gate it.
2. **The real trap is `format`.** zod's generated `date-time` validator only
   accepts a `Z` suffix. It passes today only because Pydantic v2 normalises
   tz-aware datetimes to UTC and emits `Z`.

Also learned, and worth recording because it nearly produced a wrong answer: a
fixture built with `json.dumps(..., default=str)` is **not** the wire format.
Python's `str(datetime)` is space-separated (`2026-09-12 01:00:00+00:00`) while
FastAPI's `response_model` serialisation is `T`+`Z`
(`2026-09-13T10:00:00Z`). Testing against the wrong one showed 56 failures that
did not exist. Fixtures for a contract test must come from the serialisation
path, not from `str()`.

## Decisions

### 1. Contract mechanism: Pydantic is the source, JSON Schema is the artifact

```
src/server/app/education/models.py            ← source of truth (already exists)
        + src/tools/homework/schemas.py       ← artifact envelope + tool args
                ↓ scripts/contracts/export_schemas.py   (new)
web/src/contracts/education-calendar.schema.json        ← committed, generated
                ↓ z.fromJSONSchema()
web/src/contracts/educationCalendar.ts       ← zod validator + z.infer types
```

Drift is possible in exactly one place — the committed JSON against Pydantic —
and one Python test regenerates and compares it. The frontend consumes the
committed file, so it cannot drift structurally at all.

**`format` is stripped by the exporter.** We want the *structure* (types,
required, arrays, nullability), not zod re-interpreting date semantics; the
frontend already handles date strings. Stripping `format` also removes the
`Z`-only trap above. This is a deliberate, documented narrowing, not an
oversight.

**No third-party generator for now.** `json-schema-to-zod` generates real zod
source (readable, hand-editable) at the cost of a dependency and a second
generation step; it does not address the `format` trap, which is the actual
problem. Revisit only when the artifact set grows into a union worth
auto-converting. The drift guard is what makes that swap safe later.

### 2. The tool

`get_homework_schedule`, in a new `src/tools/homework/` package.

**Args** must serve both "今天作业有什么" and "上周/下周这段时间":

```python
class HomeworkScheduleArgs(BaseModel):
    window: Literal[
        "today", "tomorrow", "this_week", "next_week", "last_week", "2w", "1m"
    ] | None = "2w"
    start_date: date | None = None
    end_date: date | None = None
```

- `window` covers the common asks; week semantics are resolved server-side in
  the household's timezone, reusing the backend's existing `isoweekday` week
  window rather than inventing a second week definition.
- `start_date`/`end_date` cover arbitrary ranges and must be supplied together.
- The 62-day range ceiling the calendar API already enforces is checked in the
  tool so the model gets a clear message instead of a downstream error.
- `user_id` comes from `config.configurable` (the pattern
  `src/tools/automation/tools.py` already uses); the household scope is
  resolved by the existing service.

**Data** comes from the existing `get_task_calendar(user_id, start_date,
end_date)` — the same service the dashboard widget calls. No new query code.

**Returns** `(content, artifact)`:

- `content` is a short markdown digest for the model and for history. It is
  capped (a long range can hold dozens of tasks and this is read into context),
  with a "+N more" tail.
- `artifact` is the payload the card renders. Because a chat artifact cannot
  fetch, it must be **self-contained**: it carries the resolved **child names**
  and the household **timezone**, which the dashboard widget gets from two
  extra API calls. This is the concrete reason the two components diverge.

Envelope:

```python
class HomeworkScheduleArtifact(BaseModel):
    type: Literal["homework_schedule"] = "homework_schedule"
    window: str | None
    start_date: date
    end_date: date
    timezone: str
    stats: EducationCalendarStatsResponse
    days: list[EducationCalendarDayResponse]
    student_names: dict[str, str]
```

### 3. Frontend: copy the widget, do not extract it

The dashboard widget is a *container*: it fetches, is config-driven, is aware of
edit mode and registers a context exporter. The chat artifact is a *leaf*: it
renders a payload and must reproduce identically on replay from stored events.

Per the review decision, the chat card is a **copy** of the widget's rendering
that is free to diverge, not a shared extraction: the widget is an ordinary
product component and this is the first member of a new agent-facing family.
Two consequences to hold onto:

- The copy starts from `HomeworkCalendarWidget.tsx` and keeps the parts worth
  keeping (bucket definitions, `bucketFor`, `dayDots`, the row, the month
  grid, `SubjectIcon`, the existing locale keys).
- It drops the container-only machinery: `useEducationTaskCalendar`,
  `useEducationMembers`, `useAuth`, `updateConfig`, `useWidgetContextExport`,
  `RowAttachButton` (which requires a registered exporter), and the view/range
  controls that exist to write prefs.

The generated contract is what keeps the two honest: both sides derive their
types from the same Pydantic models, so a change to the payload shape fails the
drift test rather than silently breaking one of them.

### 4. Card content

The card leads with "最近" — the stats strip plus the day-grouped list
(today / tomorrow / this week / later, in that order), which is the direct
answer to the question that triggers it. The month grid is carried over in the
copy but is not the default; it renders when the artifact's range spans a whole
month.

### 5. Exposure: Flash and PTC both

Both agents get the tool, per the review decision. This is a deliberate change
to Flash's stated boundary — `src/ptc_agent/agent/flash/agent.py` documents
itself as "External tools only (no sandbox, no MCP)". A first-party,
household-scoped read is consistent with the family product even though it is
not "external", so the tool joins Flash's list **and that docstring is updated
in the same commit** rather than left contradicting the code.

Managed teaching jobs must not get it: they are scoped to one chapter's
materials, and the existing `managed_policy is None` guard is the precedent to
follow.

## Risks

1. **Replay.** A chat card must render from stored history, not a live fetch.
   Whether the tool artifact survives into the history projection has not been
   checked yet; the plan verifies it explicitly and treats a miss as a blocker
   rather than a follow-up.
2. **Flash boundary drift.** Adding a DB-reading tool to Flash is a product
   boundary change. It is recorded here and in the code comment so the next
   reader sees the intent, not an accident.
3. **Contract scope creep.** The temptation is to model every artifact as one
   discriminated union now. This design deliberately scopes to one payload
   shape; the union is a separate piece of work with its own design.
4. **Two components to keep in step.** The copy is intentional, but the widget
   and the card share locale keys and subject-icon mapping. Extracting those
   two shared pieces is in scope; extracting the view layer is not.

## Out of scope

- A global artifact registry, discriminators across artifact types, or
  validating existing finance/web artifacts.
- Backfilling `type` onto artifacts that do not have one.
- Reworking the ~20 existing `as Record<string, unknown>` read sites.
