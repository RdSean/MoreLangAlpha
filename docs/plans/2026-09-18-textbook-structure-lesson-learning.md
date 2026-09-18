# Textbook Structure, Per-KP Lesson, and Learning Experience Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a reviewable textbook structure layer, generate one Markdown lesson per reviewed knowledge point, publish immutable lesson snapshots, and provide a Mentrix-style chapter and knowledge-point learning experience using LangAlpha's own visual style.

**Architecture:** The library remains responsible only for high-fidelity Markdown and assets. Textbook processing starts with a service-owned structure job that produces persistent Unit and knowledge-point records with source locators and confidence. Each knowledge point then generates an independent Markdown lesson, with optional structured practice only when auto-grading is required. Published lessons are frozen by publication snapshot; student questions, highlights, notes, progress, and personalized summaries remain separate personal data.

**Tech Stack:** Python 3.13+, FastAPI, async psycopg3, Alembic raw SQL, Pydantic, PostgreSQL, Redis, MinIO/S3-compatible storage, managed PTC runs, React 19, React Router, TypeScript, React Query, Tailwind/shadcn, Vitest, Playwright, pytest, Ruff.

---

## Fixed Product Decisions

- The library does not perform TOC or Unit analysis during document parsing.
- Structure analysis starts only after a parent explicitly creates a textbook processing job.
- A structure version is a persistent, reviewable asset with Unit and knowledge-point identity.
- Source evidence and confidence belong to the structure layer, not to every lesson.
- A lesson's primary payload is `lesson.md`.
- `vocabulary`, formulas, grammar, examples, and ordinary exercises stay inside Markdown unless a real consumer needs structured data.
- `practice.json` is optional and exists only when questions participate in auto-grading, mastery tracking, or a wrong-answer collection.
- The first version does not require `evidence.json`, `vocabulary.json`, or `profile.json` inside each lesson.
- Processing profiles customize pedagogy and skill selection but cannot change the base asset contract or object paths.
- Official lesson revisions are immutable. Regeneration creates a new revision.
- Student-owned questions, answers, highlights, notes, and summaries never mutate official lesson revisions.
- UI interaction follows Mentrix's chapter tree, knowledge-point course, follow-up, personalized-summary, highlight, and annotation patterns.
- Visual theme stays native to LangAlpha; Mentrix is an interaction reference, not a visual-design source.
- Markdown rendering is behind an education-specific component so the rendering style can be replaced without changing lesson pages or API contracts.

## Target Flow

```text
Textbook content version
  -> structure generation job
  -> structure review
  -> Unit review
  -> knowledge-point review
  -> per-knowledge-point lesson generation
  -> lesson review
  -> publication snapshot
  -> student learning
  -> questions / highlights / notes / summaries
```

## Target Backend Shape

```text
POST /api/v1/education/textbook-versions/{version_id}/structures
GET  /api/v1/education/textbook-structures/{structure_id}
POST /api/v1/education/textbook-structures/{structure_id}/review
POST /api/v1/education/textbook-structures/{structure_id}/lessons
POST /api/v1/education/knowledge-points/{knowledge_point_id}/lessons
GET  /api/v1/education/knowledge-point-lessons/{lesson_id}
POST /api/v1/education/knowledge-point-lessons/{lesson_id}/review
GET  /api/v1/education/learning/{assignment_id}/structure
GET  /api/v1/education/learning/{assignment_id}/knowledge-points/{knowledge_point_id}
POST /api/v1/education/learning/{assignment_id}/knowledge-points/{knowledge_point_id}/progress
POST /api/v1/education/learning/{assignment_id}/knowledge-points/{knowledge_point_id}/items
```

## Target Frontend Shape

Parent authoring:

```text
/education/textbooks/:textbookId/versions/:versionId/structure
/education/textbooks/:textbookId/versions/:versionId/structure/units/:unitId
/education/textbooks/:textbookId/versions/:versionId/knowledge/:knowledgePointId
```

Student learning:

```text
/education/learn/:assignmentId
/education/learn/:assignmentId/units/:unitId
/education/learn/:assignmentId/knowledge/:knowledgePointId
/education/learn/:assignmentId/summary
```

The existing `/education/learn/:assignmentId/:chapterId?` route redirects to the unit route for backward compatibility.

## UI Interaction Specification

### Shared Textbook Workspace

Create one responsive layout primitive used by both parent review and student learning:

```text
TextbookWorkspaceLayout
  Header
    textbook title
    Unit and knowledge-point breadcrumb
    mode switch: 知识点学习 | 个性化总结
    progress summary
  Left Rail
    chapter tree
    Unit completion count
    knowledge-point status icons
  Main Band
    Unit home, lesson Markdown, or summary
  Right Rail
    unit statistics
    lesson outline
    personal notebook
  Mobile
    left rail in drawer
    right rail in bottom sheet
```

Do not place the page layout inside a floating card. Use full-width bands, a stable left rail, and a stable right rail. Cards are reserved for repeated knowledge-point items, notes, and modals.

### Parent Structure Review

The structure review page contains:

- A chapter tree with review state and confidence badges.
- A Unit detail band showing source coverage and mapped original excerpts.
- A knowledge-point table with title, source locator, confidence, and review action.
- Actions to accept, rename, merge, split, delete, or add a knowledge point.
- A persistent warning when source coverage is incomplete.
- A lesson-generation action that is disabled until all blocking structure issues are resolved.

### Parent Lesson Review

The lesson review page contains:

- Markdown lesson preview using `EducationMarkdown`.
- Source locator links that open the original textbook excerpt.
- Revision history and generation profile metadata.
- Actions to approve, request regeneration, or edit the official Markdown.
- Optional practice preview only when the lesson has a structured practice asset.

### Student Learning

The knowledge-point learning page contains:

- Left knowledge-point tree grouped by Unit.
- Main Markdown lesson rendered through `EducationMarkdown`.
- A bottom follow-up composer bound to the current knowledge point.
- A right portable notebook containing the lesson outline, highlights, notes, and saved questions.
- Source-locator links that jump to the original textbook excerpt.
- Previous and next knowledge-point navigation.

The personalized-summary page contains:

- Unit progress and study counts.
- Learned, review-needed, and not-started knowledge points.
- Questions, highlights, notes, and lesson references grouped by knowledge point.
- A generated review note action. The generated note is personal learning data and does not alter the official lesson.

## Data Model

### Migration 066: Structure and Generation

Create:

```text
education_textbook_structures
  structure_id UUID PRIMARY KEY
  version_id UUID NOT NULL REFERENCES education_textbook_versions(version_id)
  sequence INTEGER NOT NULL
  status VARCHAR(24) NOT NULL
  schema_version VARCHAR(32) NOT NULL
  processing_profile_id UUID
  processing_profile_sha256 VARCHAR(64) NOT NULL
  input_manifest_sha256 VARCHAR(64) NOT NULL
  source_revision VARCHAR(64) NOT NULL
  created_by_user_id VARCHAR(255) NOT NULL
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
  reviewed_at TIMESTAMPTZ

education_structure_units
  unit_id UUID PRIMARY KEY
  structure_id UUID NOT NULL REFERENCES education_textbook_structures(structure_id)
  position INTEGER NOT NULL
  slug VARCHAR(255) NOT NULL
  title VARCHAR(255) NOT NULL
  summary TEXT NOT NULL DEFAULT ''
  unit_type VARCHAR(32) NOT NULL
  source_refs JSONB NOT NULL DEFAULT '[]'::jsonb
  confidence REAL NOT NULL
  status VARCHAR(24) NOT NULL
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()

education_structure_knowledge_points
  knowledge_point_id UUID PRIMARY KEY
  unit_id UUID NOT NULL REFERENCES education_structure_units(unit_id)
  position INTEGER NOT NULL
  slug VARCHAR(255) NOT NULL
  title VARCHAR(255) NOT NULL
  summary TEXT NOT NULL DEFAULT ''
  source_refs JSONB NOT NULL DEFAULT '[]'::jsonb
  confidence REAL NOT NULL
  status VARCHAR(24) NOT NULL
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()

education_generation_jobs
  generation_job_id UUID PRIMARY KEY
  version_id UUID NOT NULL REFERENCES education_textbook_versions(version_id)
  scope VARCHAR(24) NOT NULL
  structure_id UUID REFERENCES education_textbook_structures(structure_id)
  knowledge_point_id UUID REFERENCES education_structure_knowledge_points(knowledge_point_id)
  status VARCHAR(24) NOT NULL
  attempt_count INTEGER NOT NULL DEFAULT 0
  processing_profile_sha256 VARCHAR(64) NOT NULL
  error_code VARCHAR(64)
  error_message TEXT
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()

education_generation_attempts
  attempt_id UUID PRIMARY KEY
  generation_job_id UUID NOT NULL REFERENCES education_generation_jobs(generation_job_id)
  previous_attempt_id UUID REFERENCES education_generation_attempts(attempt_id)
  managed_workspace_id UUID NOT NULL REFERENCES workspaces(workspace_id)
  managed_thread_id UUID NOT NULL REFERENCES conversation_threads(conversation_thread_id)
  root_run_id UUID REFERENCES conversation_responses(conversation_response_id)
  status VARCHAR(24) NOT NULL
  error_code VARCHAR(64)
  error_message TEXT
  started_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
  heartbeat_at TIMESTAMPTZ
  completed_at TIMESTAMPTZ
```

`scope` is `structure` or `lesson`. Exactly one of `structure_id` and `knowledge_point_id` is set for lesson jobs. Enforce this with a check constraint.

### Migration 067: Lessons and Publication Freeze

Create:

```text
education_kp_lessons
  lesson_id UUID PRIMARY KEY
  knowledge_point_id UUID NOT NULL REFERENCES education_structure_knowledge_points(knowledge_point_id)
  status VARCHAR(24) NOT NULL
  latest_revision_id UUID
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
  reviewed_at TIMESTAMPTZ

education_kp_lesson_revisions
  revision_id UUID PRIMARY KEY
  lesson_id UUID NOT NULL REFERENCES education_kp_lessons(lesson_id)
  revision INTEGER NOT NULL
  format VARCHAR(24) NOT NULL DEFAULT 'markdown'
  content_key TEXT NOT NULL
  content_sha256 VARCHAR(64) NOT NULL
  size_bytes INTEGER NOT NULL
  processing_profile_sha256 VARCHAR(64) NOT NULL
  generation_job_id UUID REFERENCES education_generation_jobs(generation_job_id)
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()

education_publication_kp_lessons
  publication_id UUID NOT NULL REFERENCES education_textbook_publications(publication_id)
  knowledge_point_id UUID NOT NULL REFERENCES education_structure_knowledge_points(knowledge_point_id)
  lesson_revision_id UUID NOT NULL REFERENCES education_kp_lesson_revisions(revision_id)
  PRIMARY KEY (publication_id, knowledge_point_id)
```

### Migration 068: Student Personal Learning Assets

Create:

```text
education_learning_kp_progress
  assignment_id UUID NOT NULL REFERENCES education_textbook_assignments(assignment_id)
  knowledge_point_id UUID NOT NULL REFERENCES education_structure_knowledge_points(knowledge_point_id)
  status VARCHAR(24) NOT NULL
  started_at TIMESTAMPTZ
  completed_at TIMESTAMPTZ
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
  PRIMARY KEY (assignment_id, knowledge_point_id)

education_learning_items
  item_id UUID PRIMARY KEY
  assignment_id UUID NOT NULL REFERENCES education_textbook_assignments(assignment_id)
  knowledge_point_id UUID NOT NULL REFERENCES education_structure_knowledge_points(knowledge_point_id)
  kind VARCHAR(24) NOT NULL
  content TEXT NOT NULL
  source_anchor JSONB
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
```

`kind` initially supports `question`, `highlight`, `note`, and `summary`.

---

### Task 1: Add Structure and Generation Database Contracts

**Files:**
- Create: `migrations/versions/066_add_textbook_structure_models.py`
- Modify: `src/server/database/education_textbooks.py`
- Create: `tests/unit/migrations/test_education_structure_models.py`
- Create: `tests/unit/server/database/test_education_structure_models.py`

**Step 1: Write the failing migration test**

Assert the migration adds the structure, Unit, knowledge-point, generation-job, and generation-attempt tables. Assert the scope check requires exactly one target.

```python
def test_structure_migration_enforces_one_generation_target():
    sql = migration_module.upgrade_sql
    assert "CREATE TABLE education_textbook_structures" in sql
    assert "CREATE TABLE education_structure_units" in sql
    assert "CREATE TABLE education_structure_knowledge_points" in sql
    assert "CHECK (" in sql
    assert "scope = 'structure'" in sql
    assert "scope = 'lesson'" in sql
```

**Step 2: Run the test to verify it fails**

Run:

```bash
uv run pytest tests/unit/migrations/test_education_structure_models.py -q
```

Expected: FAIL because migration 066 does not exist.

**Step 3: Add migration 066**

Use raw SQL through `op.execute`, matching the repository's Alembic style. Add unique constraints:

```sql
UNIQUE (version_id, sequence)
UNIQUE (structure_id, position)
UNIQUE (unit_id, position)
UNIQUE (unit_id, slug)
```

Add indexes for version lookup, structure lookup, job status, and knowledge-point lookup.

**Step 4: Add database repository functions with failing tests**

Add tests for:

- Creating the first structure version for a content version.
- Rejecting a structure version for a foreign textbook household.
- Creating a structure generation job.
- Creating a lesson generation job for one knowledge point.
- Rejecting a generation job with both or neither target.

Run:

```bash
uv run pytest tests/unit/server/database/test_education_structure_models.py -q
```

Expected: FAIL before repository implementation.

**Step 5: Implement repository functions**

Add to `src/server/database/education_textbooks.py`:

```python
async def create_textbook_structure(...)
async def get_textbook_structure_for_parent(...)
async def create_structure_units_and_knowledge_points(...)
async def create_generation_job(...)
async def claim_generation_job(...)
async def settle_generation_job(...)
```

All parent queries must join through `education_memberships` and require `role = 'parent'`.

**Step 6: Run the tests and commit**

Run:

```bash
uv run pytest tests/unit/migrations/test_education_structure_models.py \
  tests/unit/server/database/test_education_structure_models.py -q
uv run ruff check src/server/database/education_textbooks.py
```

Expected: PASS.

Commit:

```bash
git add migrations/versions/066_add_textbook_structure_models.py \
  src/server/database/education_textbooks.py \
  tests/unit/migrations/test_education_structure_models.py \
  tests/unit/server/database/test_education_structure_models.py
git commit -m "feat(education): persist textbook structures and generation jobs"
```

### Task 2: Add Structure Asset Validation

**Files:**
- Create: `src/server/services/education_structure_validation.py`
- Create: `tests/unit/server/services/test_education_structure_validation.py`

**Step 1: Write failing tests**

Cover:

- Valid `structure.json` with two Units and nested knowledge points.
- Rejection when a Unit has no source refs.
- Rejection when source refs use unknown source IDs or invalid offsets.
- Rejection when a non-teaching Unit incorrectly contains generated knowledge points.
- Acceptance of an empty knowledge-point list for `front_matter`, `reference`, and `appendix`.
- Rejection of duplicate Unit or knowledge-point positions.
- Rejection of duplicate slugs within a parent.

Use this canonical input:

```python
STRUCTURE = {
    "format": "langalpha-managed-textbook-structure/v1",
    "units": [{
        "position": 1,
        "slug": "unit-1-sports",
        "title": "Unit 1: Sports and Fitness",
        "unit_type": "teaching",
        "confidence": 0.96,
        "source_refs": [{
            "source_id": "source-1",
            "start": 1200,
            "end": 4500,
            "quote": "Unit 1: Sports and Fitness",
        }],
        "knowledge_points": [{
            "position": 1,
            "slug": "world-game",
            "title": "世界运动：足球的历史与流行原因",
            "confidence": 0.93,
            "source_refs": [{
                "source_id": "source-1",
                "start": 1320,
                "end": 4100,
            }],
        }],
    }],
}
```

**Step 2: Run the tests to verify they fail**

```bash
uv run pytest tests/unit/server/services/test_education_structure_validation.py -q
```

Expected: FAIL because the module does not exist.

**Step 3: Implement the pure validator**

Create:

```python
class TextbookStructureValidationError(ValueError):
    pass


def validate_textbook_structure(
    candidate: object,
    frozen_input: Mapping[str, Any],
) -> dict[str, Any]:
    ...
```

Validate:

- Exact format string.
- At least one Unit.
- Unit positions and slugs are unique.
- Every Unit has at least one valid source range.
- Teaching Units may contain zero or more knowledge points.
- Non-teaching Units must contain zero knowledge points.
- Knowledge-point positions and slugs are unique within a Unit.
- Knowledge-point confidence is between 0 and 1.
- Source offsets are positive and ordered.
- Source IDs belong to the frozen input.

Normalize output to a service-controlled shape. Do not use model-provided IDs.

**Step 4: Run tests and commit**

```bash
uv run pytest tests/unit/server/services/test_education_structure_validation.py -q
uv run ruff check src/server/services/education_structure_validation.py
```

Expected: PASS.

```bash
git add src/server/services/education_structure_validation.py \
  tests/unit/server/services/test_education_structure_validation.py
git commit -m "feat(education): validate textbook structure assets"
```

### Task 3: Add Structure Generation Through Managed PTC

**Files:**
- Create: `src/server/services/education_structure_jobs.py`
- Modify: `src/server/services/education_teaching_storage.py`
- Modify: `src/ptc_agent/agent/managed_execution.py`
- Modify: `plugins/langalpha_local/skills/book-to-skill/SKILL.md`
- Modify: `plugins/langalpha_local/skills/book-to-skill/reference/managed-textbook-contract.md`
- Create: `tests/unit/server/services/test_education_structure_jobs.py`
- Modify: `tests/unit/ptc_agent/test_managed_textbook_skill_contracts.py`

**Step 1: Write failing structure-job tests**

Cover:

- Staging uploads `inputs/manifest.json` and source Markdown.
- Prompt limits the output to `outputs/structure.json`.
- The structure skill is told not to force knowledge points for non-teaching Units.
- The job records input-manifest and skill hashes.
- A valid structure output is validated and persisted.
- Invalid output fails only the structure job.

**Step 2: Run the tests to verify they fail**

```bash
uv run pytest tests/unit/server/services/test_education_structure_jobs.py -q
```

Expected: FAIL.

**Step 3: Add managed structure policy**

Add:

```python
def education_structure_policy(job_id: str) -> ManagedExecutionPolicy:
    return ManagedExecutionPolicy(
        allowed_skill_names=frozenset({"book-to-skill"}),
        filesystem_root=f"/managed/textbook-job/{UUID(job_id)}",
        allow_subagents=True,
    )
```

Allow writes only to:

```text
outputs/structure.json
```

Do not allow lesson generation or teaching-package generation in this job.

**Step 4: Add the structure prompt and skill contract**

The prompt must state:

- The parser does not guarantee Unit or TOC boundaries.
- The model must identify teaching Units and non-teaching sections.
- A non-teaching section may have an empty knowledge-point list.
- Every Unit and knowledge point must include source locators.
- The model must not manufacture knowledge points to satisfy a count.
- The only output is strict `outputs/structure.json`.

Add a `Managed textbook structure mode` section to `book-to-skill/SKILL.md`. Do not execute normal PDF extraction, generated skill files, memory, or HTML output.

**Step 5: Implement the service and persistence**

Create `src/server/services/education_structure_jobs.py` with:

```python
async def queue_structure_generation(...)
async def dispatch_structure_generation(...)
async def finalize_structure_generation(...)
async def resume_structure_generation(...)
```

Store the validated structure and all Unit and knowledge-point rows in one PostgreSQL transaction. Store the raw `structure.json` under the private `education/` bundle after validation.

**Step 6: Run tests and commit**

```bash
uv run pytest tests/unit/server/services/test_education_structure_jobs.py \
  tests/unit/ptc_agent/test_managed_textbook_skill_contracts.py -q
uv run ruff check src/server/services/education_structure_jobs.py \
  src/ptc_agent/agent/managed_execution.py
```

Expected: PASS.

```bash
git add src/server/services/education_structure_jobs.py \
  src/server/services/education_teaching_storage.py \
  src/ptc_agent/agent/managed_execution.py \
  plugins/langalpha_local/skills/book-to-skill/SKILL.md \
  plugins/langalpha_local/skills/book-to-skill/reference/managed-textbook-contract.md \
  tests/unit/server/services/test_education_structure_jobs.py \
  tests/unit/ptc_agent/test_managed_textbook_skill_contracts.py
git commit -m "feat(education): generate reviewable textbook structures"
```

### Task 4: Add Structure Review API

**Files:**
- Modify: `src/server/app/education/models.py`
- Modify: `src/server/app/education/textbooks.py`
- Modify: `src/server/services/education_textbooks.py`
- Create: `tests/unit/server/app/education/test_textbook_structures.py`
- Modify: `tests/unit/server/services/test_education_textbooks.py`

**Step 1: Write failing service and API tests**

Cover:

- Parent can create a structure job for a reviewable content version.
- Parent can read structure details with Units and knowledge points.
- Parent can rename a Unit or knowledge point.
- Parent can merge, split, delete, and add knowledge points.
- Another household receives 404.
- Student receives 403.
- Structure review transitions from `review` to `accepted`.

**Step 2: Run the tests to verify they fail**

```bash
uv run pytest tests/unit/server/app/education/test_textbook_structures.py \
  tests/unit/server/services/test_education_textbooks.py -q
```

Expected: FAIL.

**Step 3: Add Pydantic response and request models**

Add:

```python
class TextbookStructureResponse(BaseModel):
    structure_id: UUID
    version_id: UUID
    sequence: int
    status: Literal["queued", "running", "review", "accepted", "failed"]
    units: list[TextbookStructureUnitResponse]


class UpdateStructureUnitRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)


class UpdateKnowledgePointRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
```

**Step 4: Add routes**

Add:

```python
@router.post(
    "/textbook-versions/{version_id}/structures",
    response_model=TextbookStructureResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_family_textbook_structure(...):
    ...


@router.get(
    "/textbook-structures/{structure_id}",
    response_model=TextbookStructureResponse,
)
async def get_family_textbook_structure(...):
    ...


@router.post(
    "/textbook-structures/{structure_id}/review",
    response_model=TextbookStructureResponse,
)
async def accept_family_textbook_structure(...):
    ...
```

**Step 5: Run tests and commit**

```bash
uv run pytest tests/unit/server/app/education/test_textbook_structures.py \
  tests/unit/server/services/test_education_textbooks.py -q
uv run ruff check src/server/app/education/models.py \
  src/server/app/education/textbooks.py \
  src/server/services/education_textbooks.py
```

Expected: PASS.

```bash
git add src/server/app/education/models.py \
  src/server/app/education/textbooks.py \
  src/server/services/education_textbooks.py \
  tests/unit/server/app/education/test_textbook_structures.py \
  tests/unit/server/services/test_education_textbooks.py
git commit -m "feat(education): expose textbook structure review APIs"
```

### Task 5: Add Per-KP Lesson Storage and Publication Freeze

**Files:**
- Create: `migrations/versions/067_add_kp_lessons.py`
- Modify: `src/server/database/education_textbooks.py`
- Modify: `src/server/services/education_teaching_storage.py`
- Create: `tests/unit/migrations/test_kp_lessons.py`
- Modify: `tests/unit/server/database/test_education_structure_models.py`

**Step 1: Write failing migration and repository tests**

Cover:

- Lesson revisions are immutable and ordered per lesson.
- Only one latest revision ID is projected on `education_kp_lessons`.
- Publishing records one lesson revision for every published knowledge point.
- A publication cannot reference a knowledge point outside its structure.

**Step 2: Run the tests to verify they fail**

```bash
uv run pytest tests/unit/migrations/test_kp_lessons.py \
  tests/unit/server/database/test_education_structure_models.py -q
```

Expected: FAIL.

**Step 3: Add migrations 067**

Add the tables and indexes exactly as specified in the data model section. Use `ON DELETE RESTRICT` for published lesson revisions.

**Step 4: Add storage helpers**

Use this private path:

```text
education/<household>/<textbook>/v<version>/structures/v<structure-sequence>/
  units/<unit-position>-<unit-slug>/
    knowledge-points/<kp-position>-<kp-slug>/
      lessons/v<lesson-revision>/lesson.md
```

Store `content_key`, `content_sha256`, and `size_bytes` in PostgreSQL. Never return the storage key to the browser.

**Step 5: Add repository functions**

Add:

```python
async def create_kp_lesson(...)
async def create_kp_lesson_revision(...)
async def get_kp_lesson_for_parent(...)
async def freeze_publication_lessons(...)
async def get_published_kp_lesson(...)
```

**Step 6: Run tests and commit**

```bash
uv run pytest tests/unit/migrations/test_kp_lessons.py \
  tests/unit/server/database/test_education_structure_models.py -q
uv run ruff check src/server/database/education_textbooks.py
```

Expected: PASS.

```bash
git add migrations/versions/067_add_kp_lessons.py \
  src/server/database/education_textbooks.py \
  src/server/services/education_teaching_storage.py \
  tests/unit/migrations/test_kp_lessons.py \
  tests/unit/server/database/test_education_structure_models.py
git commit -m "feat(education): persist immutable knowledge-point lessons"
```

### Task 6: Generate One Markdown Lesson Per Knowledge Point

**Files:**
- Create: `src/server/services/education_lesson_jobs.py`
- Create: `src/server/services/education_lesson_validation.py`
- Modify: `src/server/services/education_teaching_storage.py`
- Modify: `src/ptc_agent/agent/managed_execution.py`
- Modify: `plugins/langalpha_local/skills/the-knowledge-guy/SKILL.md`
- Modify: `plugins/langalpha_local/skills/the-knowledge-guy/reference/managed-textbook-contract.md`
- Create: `tests/unit/server/services/test_education_lesson_jobs.py`
- Create: `tests/unit/server/services/test_education_lesson_validation.py`
- Modify: `tests/unit/ptc_agent/test_managed_textbook_skill_contracts.py`

**Step 1: Write failing lesson validation tests**

Cover:

- Valid `lesson.md` is accepted.
- Empty Markdown and oversized Markdown are rejected.
- Exact knowledge-point ID and content hash are preserved in the job envelope.
- Optional `practice.json` is accepted only when auto-grading is requested.
- Vocabulary, formulas, grammar, and written exercises are not required as top-level JSON.

**Step 2: Write failing lesson-job tests**

Cover:

- A lesson job receives only the target knowledge point, related source slices, Unit context, and processing profile.
- A lesson job writes only `outputs/lesson.md` and optional `outputs/practice.json`.
- Regeneration creates a new revision and does not overwrite the previous revision.
- A failed lesson job does not fail sibling lesson jobs.

**Step 3: Run tests to verify they fail**

```bash
uv run pytest tests/unit/server/services/test_education_lesson_validation.py \
  tests/unit/server/services/test_education_lesson_jobs.py -q
```

Expected: FAIL.

**Step 4: Implement the lesson contract**

The lesson prompt must receive:

```text
knowledge_point_id
knowledge_point_title
unit_title
source locators and exact source excerpts
processing profile
optional structured-practice flag
```

The prompt must not receive the entire book.

The output contract is:

```text
outputs/lesson.md
outputs/practice.json   # optional
```

`lesson.md` may contain headings, tables, blockquotes, vocabulary lists, formulas, examples, questions, and review prompts.

**Step 5: Implement the lesson service**

Create:

```python
async def queue_kp_lesson_generation(...)
async def dispatch_kp_lesson_generation(...)
async def finalize_kp_lesson_generation(...)
async def resume_kp_lesson_generation(...)
```

Persist only a valid lesson revision. Store regeneration errors on the generation job, not on the stable lesson identity.

**Step 6: Run tests and commit**

```bash
uv run pytest tests/unit/server/services/test_education_lesson_validation.py \
  tests/unit/server/services/test_education_lesson_jobs.py \
  tests/unit/ptc_agent/test_managed_textbook_skill_contracts.py -q
uv run ruff check src/server/services/education_lesson_jobs.py \
  src/server/services/education_lesson_validation.py
```

Expected: PASS.

```bash
git add src/server/services/education_lesson_jobs.py \
  src/server/services/education_lesson_validation.py \
  src/server/services/education_teaching_storage.py \
  src/ptc_agent/agent/managed_execution.py \
  plugins/langalpha_local/skills/the-knowledge-guy/SKILL.md \
  plugins/langalpha_local/skills/the-knowledge-guy/reference/managed-textbook-contract.md \
  tests/unit/server/services/test_education_lesson_jobs.py \
  tests/unit/server/services/test_education_lesson_validation.py \
  tests/unit/ptc_agent/test_managed_textbook_skill_contracts.py
git commit -m "feat(education): generate Markdown lessons per knowledge point"
```

### Task 7: Add Lesson Review and Publish Integration

**Files:**
- Modify: `src/server/services/education_textbooks.py`
- Modify: `src/server/database/education_textbooks.py`
- Modify: `src/server/app/education/models.py`
- Modify: `src/server/app/education/textbooks.py`
- Create: `tests/unit/server/services/test_education_lesson_review.py`
- Modify: `tests/unit/server/app/education/test_textbook_structures.py`

**Step 1: Write failing tests**

Cover:

- Parent can approve a lesson revision.
- Parent can edit official Markdown by creating a new revision.
- Parent can regenerate a lesson from a source locator.
- Publishing rejects structures with unresolved blocking Units.
- Publishing freezes the selected lesson revision for every knowledge point.
- Regenerating after publish does not alter the assigned publication.

**Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/server/services/test_education_lesson_review.py \
  tests/unit/server/app/education/test_textbook_structures.py -q
```

Expected: FAIL.

**Step 3: Add review APIs**

Add:

```text
POST /api/v1/education/knowledge-points/{knowledge_point_id}/lessons
GET  /api/v1/education/knowledge-point-lessons/{lesson_id}
POST /api/v1/education/knowledge-point-lessons/{lesson_id}/review
POST /api/v1/education/knowledge-point-lessons/{lesson_id}/revisions
```

The revision request accepts Markdown:

```python
class CreateLessonRevisionRequest(BaseModel):
    content_markdown: str = Field(min_length=1, max_length=200_000)
```

**Step 4: Update publication**

Extend `publish_textbook_version()` to require either a compatible legacy teaching package or an accepted structure with approved lessons for every publishable knowledge point.

**Step 5: Run tests and commit**

```bash
uv run pytest tests/unit/server/services/test_education_lesson_review.py \
  tests/unit/server/app/education/test_textbook_structures.py -q
uv run ruff check src/server/services/education_textbooks.py \
  src/server/database/education_textbooks.py
```

Expected: PASS.

```bash
git add src/server/services/education_textbooks.py \
  src/server/database/education_textbooks.py \
  src/server/app/education/models.py \
  src/server/app/education/textbooks.py \
  tests/unit/server/services/test_education_lesson_review.py \
  tests/unit/server/app/education/test_textbook_structures.py
git commit -m "feat(education): review lessons and freeze publication snapshots"
```

### Task 8: Add Parent Structure Review UI

**Files:**
- Create: `web/src/pages/Education/TextbookStructurePage.tsx`
- Create: `web/src/pages/Education/components/TextbookWorkspaceLayout.tsx`
- Create: `web/src/pages/Education/components/StructureTree.tsx`
- Create: `web/src/pages/Education/components/KnowledgePointTable.tsx`
- Modify: `web/src/pages/Education/api.ts`
- Modify: `web/src/pages/Education/types.ts`
- Modify: `web/src/pages/Education/queries.ts`
- Modify: `web/src/lib/queryKeys.ts`
- Modify: `web/src/components/Main/Main.tsx`
- Modify: `web/src/components/Main/routeChunks.ts`
- Create: `web/src/pages/Education/__tests__/TextbookStructurePage.test.tsx`

**Step 1: Write failing page tests**

Cover:

- Chapter tree renders Units and knowledge points.
- Non-teaching Units show no empty-knowledge-point warning.
- Teaching Units with no knowledge points show a blocking review warning.
- Unit rename updates the tree.
- Knowledge-point merge, delete, and add actions call exact APIs.
- Accept structure is disabled while blocking issues remain.

**Step 2: Run tests to verify they fail**

```bash
cd web
pnpm vitest run src/pages/Education/__tests__/TextbookStructurePage.test.tsx
```

Expected: FAIL because the page does not exist.

**Step 3: Add typed API and queries**

Add:

```ts
export interface TextbookStructureUnit {
  unit_id: string;
  position: number;
  title: string;
  unit_type: 'teaching' | 'front_matter' | 'reference' | 'appendix';
  confidence: number;
  status: 'review' | 'accepted' | 'blocked';
  source_refs: StructureSourceRef[];
  knowledge_points: TextbookKnowledgePoint[];
}
```

Add query keys:

```ts
textbookStructures: (versionId: string) =>
  [...queryKeys.education.textbooks(), versionId, 'structures'],
textbookStructure: (structureId: string) =>
  [...queryKeys.education.all, 'textbook-structures', structureId],
```

**Step 4: Build the page**

Use `TextbookWorkspaceLayout`. Keep the source-locator excerpt in a side panel or drawer. Do not embed source excerpts inside the tree.

**Step 5: Run tests, typecheck, and commit**

```bash
cd web
pnpm vitest run src/pages/Education/__tests__/TextbookStructurePage.test.tsx
pnpm typecheck
```

Expected: PASS.

```bash
git add web/src/pages/Education/TextbookStructurePage.tsx \
  web/src/pages/Education/components/TextbookWorkspaceLayout.tsx \
  web/src/pages/Education/components/StructureTree.tsx \
  web/src/pages/Education/components/KnowledgePointTable.tsx \
  web/src/pages/Education/api.ts \
  web/src/pages/Education/types.ts \
  web/src/pages/Education/queries.ts \
  web/src/lib/queryKeys.ts \
  web/src/components/Main/Main.tsx \
  web/src/components/Main/routeChunks.ts \
  web/src/pages/Education/__tests__/TextbookStructurePage.test.tsx
git commit -m "feat(web): review textbook Unit and knowledge-point structures"
```

### Task 9: Add Parent Lesson Review UI

**Files:**
- Create: `web/src/pages/Education/KnowledgePointLessonReviewPage.tsx`
- Create: `web/src/pages/Education/components/EducationMarkdown.tsx`
- Create: `web/src/pages/Education/components/LessonRevisionPanel.tsx`
- Modify: `web/src/pages/Education/api.ts`
- Modify: `web/src/pages/Education/queries.ts`
- Modify: `web/src/components/Main/Main.tsx`
- Modify: `web/src/components/Main/routeChunks.ts`
- Create: `web/src/pages/Education/__tests__/KnowledgePointLessonReviewPage.test.tsx`

**Step 1: Write failing page tests**

Cover:

- Markdown lesson renders through `EducationMarkdown`.
- Source links call the source-excerpt API.
- Approve sends only the expected revision ID.
- Regenerate creates a new revision and keeps the old revision visible.
- Edit Markdown creates a revision and does not mutate the previous revision.

**Step 2: Run tests to verify they fail**

```bash
cd web
pnpm vitest run src/pages/Education/__tests__/KnowledgePointLessonReviewPage.test.tsx
```

Expected: FAIL.

**Step 3: Implement `EducationMarkdown`**

Wrap the shared renderer:

```tsx
export function EducationMarkdown({
  content,
  variant = 'lesson',
  className,
}: {
  content: string;
  variant?: 'lesson' | 'summary' | 'compact';
  className?: string;
}) {
  return (
    <div data-education-markdown={variant}>
      <Markdown variant="panel" content={content} className={className} />
    </div>
  );
}
```

This is the only component that business pages import for lesson Markdown. A future renderer swap changes this file, not the pages.

**Step 4: Build the review page**

Use the shared workspace layout. Show source locators in the left context panel and revision history in the right rail.

**Step 5: Run tests, typecheck, and commit**

```bash
cd web
pnpm vitest run src/pages/Education/__tests__/KnowledgePointLessonReviewPage.test.tsx
pnpm typecheck
```

Expected: PASS.

```bash
git add web/src/pages/Education/KnowledgePointLessonReviewPage.tsx \
  web/src/pages/Education/components/EducationMarkdown.tsx \
  web/src/pages/Education/components/LessonRevisionPanel.tsx \
  web/src/pages/Education/api.ts \
  web/src/pages/Education/queries.ts \
  web/src/components/Main/Main.tsx \
  web/src/components/Main/routeChunks.ts \
  web/src/pages/Education/__tests__/KnowledgePointLessonReviewPage.test.tsx
git commit -m "feat(web): review generated knowledge-point lessons"
```

### Task 10: Add Published Learning Projection

**Files:**
- Modify: `src/server/database/education_textbooks.py`
- Modify: `src/server/services/education_textbooks.py`
- Modify: `src/server/app/education/models.py`
- Modify: `src/server/app/education/textbooks.py`
- Create: `tests/unit/server/database/test_published_structure_learning.py`
- Create: `tests/unit/server/app/education/test_published_structure_learning.py`

**Step 1: Write failing tests**

Cover:

- A student sees only the structure and lessons frozen by their assignment publication.
- A later regeneration is invisible to the student.
- Unit and knowledge-point progress is scoped to the assignment.
- A student cannot read another assignment or textbook.

**Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/server/database/test_published_structure_learning.py \
  tests/unit/server/app/education/test_published_structure_learning.py -q
```

Expected: FAIL.

**Step 3: Add student projections**

Add:

```python
async def get_assigned_textbook_structure(...)
async def get_assigned_knowledge_point_lesson(...)
```

The query joins:

```text
assignment
  -> publication
  -> publication_kp_lessons
  -> lesson revision
  -> knowledge point
  -> structure Unit
```

**Step 4: Add routes**

```text
GET /api/v1/education/learning/{assignment_id}/structure
GET /api/v1/education/learning/{assignment_id}/knowledge-points/{knowledge_point_id}
```

Return safe content only. Do not return storage keys, internal generation jobs, or unapproved revisions.

**Step 5: Run tests and commit**

```bash
uv run pytest tests/unit/server/database/test_published_structure_learning.py \
  tests/unit/server/app/education/test_published_structure_learning.py -q
uv run ruff check src/server/database/education_textbooks.py \
  src/server/services/education_textbooks.py
```

Expected: PASS.

```bash
git add src/server/database/education_textbooks.py \
  src/server/services/education_textbooks.py \
  src/server/app/education/models.py \
  src/server/app/education/textbooks.py \
  tests/unit/server/database/test_published_structure_learning.py \
  tests/unit/server/app/education/test_published_structure_learning.py
git commit -m "feat(education): expose published structure and lessons to students"
```

### Task 11: Replace the Student Learning Shell

**Files:**
- Modify: `web/src/pages/Education/StudentLearningPage.tsx`
- Create: `web/src/pages/Education/components/LearningOutline.tsx`
- Create: `web/src/pages/Education/components/UnitOverview.tsx`
- Create: `web/src/pages/Education/components/KnowledgePointList.tsx`
- Modify: `web/src/pages/Education/__tests__/StudentLearningPage.test.tsx`
- Modify: `web/src/components/Main/Main.tsx`
- Modify: `web/src/components/Main/routeChunks.ts`

**Step 1: Write failing route and layout tests**

Cover:

- `/education/learn/:assignmentId` opens the first Unit overview.
- `/education/learn/:assignmentId/units/:unitId` opens the requested Unit.
- `/education/learn/:assignmentId/knowledge/:knowledgePointId` opens the lesson.
- Saved `/education/learn/:assignmentId/:chapterId` redirects to the new Unit route.
- Mobile uses drawers for the outline and personal notebook.

**Step 2: Run tests to verify they fail**

```bash
cd web
pnpm vitest run src/pages/Education/__tests__/StudentLearningPage.test.tsx
```

Expected: FAIL.

**Step 3: Implement the shared shell**

Use:

```text
desktop: 260px outline | minmax(0, 1fr) lesson | 320px notebook
tablet: outline drawer | lesson | notebook drawer
mobile: top breadcrumb + lesson; outline and notebook are drawers/sheets
```

Keep body text line length bounded with `max-w-[760px]`. Unit and knowledge-point controls must use fixed dimensions so status changes do not shift the tree.

**Step 4: Implement Unit overview**

Show:

- Learned knowledge-point count.
- Review-needed count.
- Question, highlight, note, and summary counts.
- Knowledge-point list with status.
- Entry into personalized summary.

**Step 5: Run tests, typecheck, and commit**

```bash
cd web
pnpm vitest run src/pages/Education/__tests__/StudentLearningPage.test.tsx
pnpm typecheck
```

Expected: PASS.

```bash
git add web/src/pages/Education/StudentLearningPage.tsx \
  web/src/pages/Education/components/LearningOutline.tsx \
  web/src/pages/Education/components/UnitOverview.tsx \
  web/src/pages/Education/components/KnowledgePointList.tsx \
  web/src/pages/Education/__tests__/StudentLearningPage.test.tsx \
  web/src/components/Main/Main.tsx \
  web/src/components/Main/routeChunks.ts
git commit -m "feat(web): add Unit and knowledge-point learning shell"
```

### Task 12: Add Knowledge-Point Lesson, Follow-Up, and Markdown Adapter

**Files:**
- Create: `web/src/pages/Education/KnowledgePointLearningPage.tsx`
- Create: `web/src/pages/Education/components/LessonOutline.tsx`
- Create: `web/src/pages/Education/components/LessonFollowUp.tsx`
- Modify: `web/src/pages/Education/components/EducationMarkdown.tsx`
- Modify: `web/src/pages/Education/api.ts`
- Modify: `web/src/pages/Education/queries.ts`
- Modify: `web/src/pages/Education/types.ts`
- Create: `web/src/pages/Education/__tests__/KnowledgePointLearningPage.test.tsx`

**Step 1: Write failing tests**

Cover:

- Markdown lesson renders.
- Heading outline is generated from Markdown headings.
- Follow-up sends assignment and knowledge-point context.
- Streaming assistant output is retained for the active knowledge point.
- Previous and next knowledge-point actions use the published structure order.

**Step 2: Run tests to verify they fail**

```bash
cd web
pnpm vitest run src/pages/Education/__tests__/KnowledgePointLearningPage.test.tsx
```

Expected: FAIL.

**Step 3: Implement the lesson page**

Keep the page free of renderer-specific logic:

```tsx
<EducationMarkdown content={lesson.content_markdown} variant="lesson" />
```

The outline parser reads heading text only for navigation. It does not modify or persist the lesson.

**Step 4: Bind follow-up to knowledge point**

Update the learning-chat service to accept:

```json
{
  "assignment_id": "uuid",
  "knowledge_point_id": "uuid"
}
```

The server must reject an assignment and knowledge point pair that is not present in the frozen publication.

**Step 5: Run tests, typecheck, and commit**

```bash
cd web
pnpm vitest run src/pages/Education/__tests__/KnowledgePointLearningPage.test.tsx
pnpm typecheck
```

Expected: PASS.

```bash
git add web/src/pages/Education/KnowledgePointLearningPage.tsx \
  web/src/pages/Education/components/LessonOutline.tsx \
  web/src/pages/Education/components/LessonFollowUp.tsx \
  web/src/pages/Education/components/EducationMarkdown.tsx \
  web/src/pages/Education/api.ts \
  web/src/pages/Education/queries.ts \
  web/src/pages/Education/types.ts \
  web/src/pages/Education/__tests__/KnowledgePointLearningPage.test.tsx
git commit -m "feat(web): add knowledge-point lesson and follow-up experience"
```

### Task 13: Add Progress, Highlights, Notes, and Personalized Summary

**Files:**
- Create: `migrations/versions/068_add_learning_items.py`
- Modify: `src/server/database/education_textbooks.py`
- Modify: `src/server/services/education_textbooks.py`
- Modify: `src/server/services/education_learning_chat.py`
- Modify: `src/server/app/education/models.py`
- Modify: `src/server/app/education/textbooks.py`
- Create: `web/src/pages/Education/PersonalizedSummaryPage.tsx`
- Create: `web/src/pages/Education/components/PersonalNotebook.tsx`
- Create: `web/src/pages/Education/components/LearningItemList.tsx`
- Create: `tests/unit/server/database/test_learning_items.py`
- Create: `tests/unit/server/app/education/test_learning_items.py`
- Create: `web/src/pages/Education/__tests__/PersonalizedSummaryPage.test.tsx`

**Step 1: Write failing database and API tests**

Cover:

- Create and update a highlight with a source anchor.
- Create and update a note.
- Save a question and its answer reference.
- Upsert knowledge-point progress.
- Reject learning items outside the published assignment.
- Generate a summary from the assignment's own learning items only.

**Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/server/database/test_learning_items.py \
  tests/unit/server/app/education/test_learning_items.py -q
```

Expected: FAIL.

**Step 3: Add migration 068 and repository functions**

Implement:

```python
async def upsert_kp_progress(...)
async def create_learning_item(...)
async def update_learning_item(...)
async def delete_learning_item(...)
async def list_learning_items(...)
```

**Step 4: Add APIs**

```text
POST   /learning/{assignment_id}/knowledge-points/{kp_id}/progress
GET    /learning/{assignment_id}/knowledge-points/{kp_id}/items
POST   /learning/{assignment_id}/knowledge-points/{kp_id}/items
PATCH  /learning/{assignment_id}/items/{item_id}
DELETE /learning/{assignment_id}/items/{item_id}
POST   /learning/{assignment_id}/units/{unit_id}/summaries
```

**Step 5: Write failing summary page tests**

Cover:

- Counts match item types.
- Items are grouped by knowledge point.
- Highlight click opens the source locator.
- Generated summary appears as a personal item.
- Empty units show a useful empty state without fabricating content.

Run:

```bash
cd web
pnpm vitest run src/pages/Education/__tests__/PersonalizedSummaryPage.test.tsx
```

Expected: FAIL.

**Step 6: Implement the page and commit**

```bash
cd web
pnpm vitest run src/pages/Education/__tests__/PersonalizedSummaryPage.test.tsx
pnpm typecheck
```

Expected: PASS.

```bash
git add migrations/versions/068_add_learning_items.py \
  src/server/database/education_textbooks.py \
  src/server/services/education_textbooks.py \
  src/server/services/education_learning_chat.py \
  src/server/app/education/models.py \
  src/server/app/education/textbooks.py \
  web/src/pages/Education/PersonalizedSummaryPage.tsx \
  web/src/pages/Education/components/PersonalNotebook.tsx \
  web/src/pages/Education/components/LearningItemList.tsx \
  tests/unit/server/database/test_learning_items.py \
  tests/unit/server/app/education/test_learning_items.py \
  web/src/pages/Education/__tests__/PersonalizedSummaryPage.test.tsx
git commit -m "feat(education): add personal notes and unit summaries"
```

### Task 14: Add Per-KP Failure Recovery and Bounded Retries

**Files:**
- Modify: `src/server/services/education_lesson_jobs.py`
- Modify: `src/server/services/education_structure_jobs.py`
- Modify: `src/server/services/education_managed_ptc.py`
- Modify: `src/server/database/education_textbooks.py`
- Create: `tests/unit/server/services/test_education_generation_retries.py`

**Step 1: Write failing retry tests**

Cover:

- Invalid lesson output retries only that knowledge point.
- Two failed auto-retries project `needs_review`.
- Sibling lessons remain accepted.
- Structure validation failure retries the structure job, never lesson jobs.
- A passed validation with archive failure retries archive only.

**Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/server/services/test_education_generation_retries.py -q
```

Expected: FAIL.

**Step 3: Add retry policy**

Use:

```python
MAX_LESSON_GENERATION_ATTEMPTS = 3
```

The first validation failure is fed back to the model as a concise, machine-generated error. The second failure uses a simplified prompt. The third failure marks the lesson `needs_review`.

Never fail the entire structure because one lesson exhausted its retry budget.

**Step 4: Add user-visible actions**

Expose:

```text
retry one knowledge-point lesson
retry all failed lessons in a Unit
regenerate accepted lesson as a new revision
```

**Step 5: Run tests and commit**

```bash
uv run pytest tests/unit/server/services/test_education_generation_retries.py -q
uv run ruff check src/server/services/education_lesson_jobs.py \
  src/server/services/education_structure_jobs.py
```

Expected: PASS.

```bash
git add src/server/services/education_lesson_jobs.py \
  src/server/services/education_structure_jobs.py \
  src/server/services/education_managed_ptc.py \
  src/server/database/education_textbooks.py \
  tests/unit/server/services/test_education_generation_retries.py
git commit -m "fix(education): isolate and retry failed lesson generation"
```

### Task 15: Add Processing Profiles and Prompt Customization

**Files:**
- Create: `migrations/versions/069_add_processing_profiles.py`
- Create: `src/server/services/education_processing_profiles.py`
- Modify: `src/server/services/education_structure_jobs.py`
- Modify: `src/server/services/education_lesson_jobs.py`
- Modify: `src/server/app/education/models.py`
- Modify: `src/server/app/education/textbooks.py`
- Create: `web/src/pages/Education/components/ProcessingProfileDialog.tsx`
- Create: `tests/unit/server/services/test_education_processing_profiles.py`
- Create: `tests/unit/server/app/education/test_processing_profiles.py`
- Create: `web/src/pages/Education/__tests__/ProcessingProfileDialog.test.tsx`

**Step 1: Write failing profile tests**

Cover:

- Default profile is created when the parent does not customize anything.
- Profiles include subject, grade level, language, depth, question types, and allowed skills.
- Profile payloads are bounded and validated.
- Prompt composition includes base contract, profile, and Unit or knowledge-point context.
- Changing a profile creates a new version and does not mutate historical jobs.

**Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/server/services/test_education_processing_profiles.py \
  tests/unit/server/app/education/test_processing_profiles.py -q
```

Expected: FAIL.

**Step 3: Add the profile model**

```python
class ProcessingProfile(BaseModel):
    subject: Literal["english", "math", "chinese", "science", "other"]
    grade_band: Literal["primary", "middle", "high", "adult"]
    language: Literal["zh-CN", "en", "bilingual"]
    depth: Literal["overview", "standard", "deep"]
    question_types: list[Literal["choice", "fill", "short_answer", "mixed"]]
    prompt_fragment: str = Field(default="", max_length=2_000)
    allowed_skills: list[str] = Field(default_factory=list, max_length=8)
```

Persist profile ID, version, canonical JSON hash, and author.

**Step 4: Add the UI dialog**

The dialog appears after source selection and before structure generation. It must:

- Offer inferred defaults.
- Show subject, grade, language, depth, and question types in compact controls.
- Allow an optional custom instruction.
- Show a concise profile summary, not raw hidden prompts.
- Persist the selected profile through the API.

**Step 5: Run backend and frontend tests and commit**

```bash
uv run pytest tests/unit/server/services/test_education_processing_profiles.py \
  tests/unit/server/app/education/test_processing_profiles.py -q
cd web
pnpm vitest run src/pages/Education/__tests__/ProcessingProfileDialog.test.tsx
pnpm typecheck
```

Expected: PASS.

```bash
git add migrations/versions/069_add_processing_profiles.py \
  src/server/services/education_processing_profiles.py \
  src/server/services/education_structure_jobs.py \
  src/server/services/education_lesson_jobs.py \
  src/server/app/education/models.py \
  src/server/app/education/textbooks.py \
  web/src/pages/Education/components/ProcessingProfileDialog.tsx \
  tests/unit/server/services/test_education_processing_profiles.py \
  tests/unit/server/app/education/test_processing_profiles.py \
  web/src/pages/Education/__tests__/ProcessingProfileDialog.test.tsx
git commit -m "feat(education): configure textbook processing profiles"
```

### Task 16: Compatibility, Feature Flag, and End-to-End Acceptance

**Files:**

- Modify: `src/config/features.py`
- Modify: `config.yaml`
- Modify: `src/server/services/education_textbooks.py`
- Modify: `web/src/components/Main/Main.tsx`
- Modify: `web/e2e/documents.spec.js`
- Create: `web/e2e/education-textbook-learning.spec.js`
- Modify: `CHANGELOG.md`

**Step 1: Add a feature flag**

Add:

```python
FEATURE_CATALOG["education_structure_lessons"] = FeatureSpec(
    key="education_structure_lessons",
    default_enabled=False,
    description="Textbook structures and per-knowledge-point lessons",
)
```

Set it true only in the local development config used for acceptance.

**Step 2: Preserve legacy reading**

When a publication has frozen structure lessons, student routes use the new model.

When it does not, existing chapter Markdown and teaching-package questions remain readable through the old route.

Do not delete or rewrite legacy learning progress and answers.

**Step 3: Add end-to-end coverage**

The Playwright test must:

1. Upload or select a completed parsed textbook.
2. Choose a processing profile.
3. Generate a structure.
4. Review Unit and knowledge points.
5. Generate two knowledge-point lessons.
6. Approve and publish.
7. Assign to a student.
8. Open Unit and knowledge-point learning pages.
9. Ask a follow-up.
10. Add a highlight and note.
11. Open personalized summary.
12. Regenerate one lesson after publication and verify the student snapshot does not change.

Run:

```bash
cd web
pnpm playwright test e2e/education-textbook-learning.spec.js --project=chromium
```

Expected: PASS.

**Step 4: Add responsive verification**

Repeat the student flow at:

```text
390 x 844
1280 x 800
```

Assert:

- No horizontal overflow.
- Markdown headings and tables remain inside the main band.
- Left and right rails become drawers without covering the lesson permanently.
- Follow-up composer remains reachable.
- Status labels do not resize tree rows.

**Step 5: Run the full focused verification**

```bash
uv run pytest tests/unit/migrations/test_education_structure_models.py \
  tests/unit/migrations/test_kp_lessons.py \
  tests/unit/server/database/test_education_structure_models.py \
  tests/unit/server/services/test_education_structure_validation.py \
  tests/unit/server/services/test_education_structure_jobs.py \
  tests/unit/server/services/test_education_lesson_validation.py \
  tests/unit/server/services/test_education_lesson_jobs.py \
  tests/unit/server/services/test_education_lesson_review.py \
  tests/unit/server/app/education/test_textbook_structures.py \
  tests/unit/server/app/education/test_published_structure_learning.py -q
uv run ruff check src/server migrations/versions
cd web
pnpm vitest run src/pages/Education/__tests__/TextbookStructurePage.test.tsx \
  src/pages/Education/__tests__/KnowledgePointLessonReviewPage.test.tsx \
  src/pages/Education/__tests__/StudentLearningPage.test.tsx \
  src/pages/Education/__tests__/KnowledgePointLearningPage.test.tsx \
  src/pages/Education/__tests__/PersonalizedSummaryPage.test.tsx
pnpm typecheck
pnpm build
pnpm playwright test e2e/education-textbook-learning.spec.js --project=chromium
```

Expected: all commands PASS.

**Step 6: Update the changelog and commit**

Add a Chinese changelog entry describing:

- The reviewable structure version.
- Per-knowledge-point Markdown lessons.
- The Mentrix-style learning interactions.
- The separate student personal learning assets.
- Backward compatibility and the feature flag.

Commit:

```bash
git add src/config/features.py config.yaml \
  src/server/services/education_textbooks.py \
  web/src/components/Main/Main.tsx \
  web/e2e/documents.spec.js web/e2e/education-textbook-learning.spec.js \
  CHANGELOG.md
git commit -m "feat(education): ship structure-based textbook learning"
```

## Final Acceptance Checklist

- The library parser still performs no semantic structure analysis.
- A parent can generate and review a structure version.
- Non-teaching sections may have zero knowledge points.
- Knowledge points are source-locatable and reviewable before lesson generation.
- A lesson is a Markdown asset, not a complex mandatory JSON bundle.
- Lessons generate and retry independently.
- Practice JSON appears only for auto-graded questions.
- Publication freezes exact lesson revisions.
- Student questions, highlights, notes, and summaries never mutate official lessons.
- Regenerating an official lesson after publication does not change a student snapshot.
- The page interaction mirrors Mentrix while retaining LangAlpha styling.
- `EducationMarkdown` is the only business-facing Markdown rendering boundary.
- Legacy textbooks and assignments remain readable.
- `0.0.0.0:5177` and `0.0.0.0:8000` pass a real parent-to-student acceptance run.
