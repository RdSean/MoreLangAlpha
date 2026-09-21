# Canonical book-to-skill Migration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the forked book-to-skill inside `the-knowledge-guy` with the
canonical [virgiliojr94/book-to-skill](https://github.com/virgiliojr94/book-to-skill)
skill, run it against our frozen Databook Markdown, and make its chapter
boundaries the single authoritative source for knowledge-point content scope.

**Architecture:** The service freezes the Databook Markdown (plus assets) into
a managed job root and vendors the canonical skill there. The managed run
executes the canonical skill in two passes: an analyze pass that produces
`outputs/structure.json` (Units + Reading A/B titles + line ranges), and a
generate pass that produces per-Reading chapter knowledge files. Our backend
then slices the frozen Markdown by the analyze pass line ranges to obtain
deterministic source text, and every knowledge point is scoped to exactly one
Reading slice. Heuristic scoping (`surrounding_section_range`,
`locate_quote_approximately`, `resolve_quote_range`, window padding) is deleted
so no code path can invent a range again.

**Tech Stack:** Python 3.13 / FastAPI, psycopg + Alembic raw SQL, PTC sandbox,
React 19 + Vite, MinIO, the vendored canonical `book-to-skill` skill.

---

## Background: why the current pipeline cannot be repaired

The repository currently vendors two skills under
`plugins/langalpha_local/skills/`:

| Path | Role |
|---|---|
| `book-to-skill/` | A fork whose `reference/managed-textbook-contract.md` states: "Do not calculate `position`, line numbers, character offsets, PDF pages or bounding boxes." It may emit **only** `outputs/structure.json`. |
| `the-knowledge-guy/` | Ask / walk / course modes plus an Ingest mode that delegates to the fork above. |

Because the fork is contractually forbidden from emitting offsets, the only
structure artifact available to us is a list of Unit and knowledge-point titles
with one short `quote` each. Measured on the real Reading Explorer 3 data:

* knowledge-point `source_refs` are `{"start": null, "end": null, "quote": "...", "resolution_status": "unresolved"}` — 60 of them unresolved across the book;
* the lesson builder therefore received a 174-character excerpt and produced a 16,925-character lesson, i.e. the model filled the page from prior knowledge;
* "read the whole section" was implemented by guessing at Markdown headings, which produced a plausible but unverifiable range.

The canonical skill does not have this limitation. Its Stage 0 extractor
records **the exact character range of every chapter**, and its Stage 1 writes
one `chapters/chNN-*.md` per chapter. Measured on our own frozen Markdown:

```
$ python3 <skill>/scripts/extract.py book.md
Extracting text document: book.md
  chapters: 2 (structural)
   Workdir -> .../full_text.txt
   Meta    -> .../metadata.json
```

`metadata.json` carries `chapters_detected`, `chapters_method`,
`chapter_headings_sample` and per-source chapter records. The canonical skill
also accepts `.md` as a first-class input
(`book_to_skill/config.py`: `TEXT_EXTENSIONS = {".txt", ".text", ".md", ".markdown", ".rst", ".adoc", ".asciidoc"}`), so **we never go back to PDF**.

### Division of responsibility (the core design decision)

| Concern | Owner |
|---|---|
| PDF to high-fidelity Markdown + images | Databook (already implemented) |
| Reading the Markdown, deciding Unit and Reading A/B boundaries | canonical `book-to-skill` (LLM, Steps 0-3) |
| Per-Reading chapter knowledge files | canonical `book-to-skill` (LLM, Steps 4-9) |
| Deterministic character slicing of the frozen Markdown | our service, using the line ranges the skill reported |
| Knowledge points inside one Reading | our service + structure review (parent edits) |
| Lesson authoring | our service, fed by chapter file + source slice |

The canonical skill's own `detect_chapters.py` regex does **not** recognise
`Unit N` headings (it targets `Chapter N`, `Part N`, `Глава N`, and similar).
That is exactly why the analyze pass, where the LLM reasons about the book's
real structure, is the source of boundaries rather than the regex.

---

## Scope decisions already made

1. Delete `the-knowledge-guy` **and** the forked `book-to-skill` completely.
2. Vendor the canonical skill into the repository (option B) so managed runs are reproducible and do not depend on the operator's home directory.
3. Chapter granularity is **Reading A / Reading B** level.
4. Lesson material is **both**: the chapter knowledge file *and* the deterministically sliced source text.
5. Existing textbook data and tables are deleted; **no forward compatibility**.

---

## Target pipeline

```
PDF --Databook--> Markdown + assets
                       |
                 freeze into managed job root
                       |
        +--------------+---------------+
   pass 1 (analyze)              pass 2 (generate)
   canonical skill Steps 0-3     canonical skill Steps 4-9
   -> outputs/structure.json     -> outputs/chapters/reading-*.md
      units[] + reading A/B        + glossary/patterns/cheatsheet
      + line_start/line_end
        +--------------+---------------+
                       v
        import: slice frozen Markdown by line range
                       v
   education_textbook_scopes  (authoritative reading ranges)
   education_structure_*      (knowledge points inside one scope)
   education_kp_lessons       (lesson + practice)
```

---

### Task 1: Remove the forked skills and every reference to them

**Files:**
- Delete: `plugins/langalpha_local/skills/the-knowledge-guy/` (whole directory)
- Delete: `plugins/langalpha_local/skills/book-to-skill/` (whole directory)
- Modify: `src/ptc_agent/agent/managed_execution.py` (policy allow-list)
- Modify: `src/ptc_agent/agent/middleware/skills/registry.py` (the two `SkillDefinition` entries)
- Modify: `src/server/services/education_teaching_storage.py` (`_MANAGED_SKILL_NAMES`)
- Modify: `src/server/services/education_teaching_jobs.py` (prompt text naming both skills)
- Modify: `src/server/services/education_textbooks.py` (`knowledge_foundations`, `book_to_skill_sha256`, `knowledge_guy_sha256`)
- Modify: `src/server/services/education_textbook_storage.py` (manifest README)
- Test: `tests/unit/server/services/test_education_teaching_storage.py`

**Step 1: Write the failing test**

```python
def test_managed_skill_names_exclude_removed_forks():
    from src.server.services import education_teaching_storage as storage

    assert "the-knowledge-guy" not in storage._MANAGED_SKILL_NAMES
    assert storage._MANAGED_SKILL_NAMES == ("book-to-skill",)
```

**Step 2: Run it to verify it fails**

Run: `uv run pytest tests/unit/server/services/test_education_teaching_storage.py -k removed_forks -v`
Expected: FAIL — the current tuple contains both skills.

**Step 3: Delete the directories and repoint every reference**

```bash
git rm -r plugins/langalpha_local/skills/the-knowledge-guy
git rm -r plugins/langalpha_local/skills/book-to-skill
```

Replace the policy allow-list:

```python
def education_structure_policy(job_id: str) -> ManagedExecutionPolicy:
    """Return the fixed policy for one canonical structure job."""
    normalized_job_id = str(UUID(job_id))
    return ManagedExecutionPolicy(
        allowed_skill_names=frozenset({"book-to-skill"}),
        filesystem_root=f"/managed/textbook-job/{normalized_job_id}",
        allow_subagents=True,
    )
```

**Step 4: Run the test and the storage suite**

Run: `uv run pytest tests/unit/server/services/test_education_teaching_storage.py -q`
Expected: PASS.

**Step 5: Grep for stragglers**

Run: `rg -n "the-knowledge-guy" src plugins docs`
Expected: no matches outside `docs/plans/` historical documents.

**Step 6: Commit**

```bash
git add -A
git commit -m "refactor(textbooks): remove forked knowledge-guy book-to-skill"
```

---

### Task 2: Vendor the canonical skill

**Files:**
- Create: `plugins/langalpha_local/skills/book-to-skill/` (copy of `/Users/seanlee/.workbuddy/skills/book-to-skill` without `.git`, `__pycache__`, `.DS_Store`, `.venv`)
- Create: `plugins/langalpha_local/skills/book-to-skill/VENDOR.md`
- Modify: `src/server/services/education_teaching_storage.py` (staged suffixes)
- Test: `tests/unit/server/services/test_education_teaching_storage.py`

**Step 1: Write the failing test**

```python
def test_canonical_skill_is_vendored_with_its_extractor():
    from src.server.services.education_teaching_storage import managed_skill_source_root

    root = managed_skill_source_root("book-to-skill")
    assert (root / "SKILL.md").is_file()
    assert (root / "scripts" / "extract.py").is_file()
    assert (root / "book_to_skill" / "parsers" / "text.py").is_file()
```

**Step 2: Run it to verify it fails**

Run: `uv run pytest tests/unit/server/services/test_education_teaching_storage.py -k canonical_skill -v`
Expected: FAIL — the helper does not exist.

**Step 3: Copy the skill and record provenance**

```bash
mkdir -p plugins/langalpha_local/skills/book-to-skill
rsync -a --exclude '.git' --exclude '__pycache__' --exclude '.DS_Store' --exclude '.venv' \
  /Users/seanlee/.workbuddy/skills/book-to-skill/ \
  plugins/langalpha_local/skills/book-to-skill/
```

`VENDOR.md` records the upstream URL, the vendoring date, and the local
deviations (none at vendoring; Task 3 adds the managed overlay).

Extend the stager so executable helper scripts are staged too:

```python
_STATIC_SKILL_SUFFIXES = frozenset({".css", ".html", ".json", ".md", ".py", ".toml"})
```

**Step 4: Run the test**

Run: `uv run pytest tests/unit/server/services/test_education_teaching_storage.py -q`
Expected: PASS.

**Step 5: Commit**

```bash
git add -A
git commit -m "feat(textbooks): vendor canonical book-to-skill"
```

---

### Task 3: Add the managed analyze prompt for the canonical skill

**Files:**
- Create: `plugins/langalpha_local/skills/book-to-skill/reference/langalpha-managed.md`
- Modify: `src/server/services/education_structure_jobs.py` (`managed_structure_prompt`)
- Test: `tests/unit/server/services/test_education_structure_jobs.py`

**Step 1: Write the failing test**

```python
def test_managed_structure_prompt_requests_reading_ranges():
    prompt = education_structure_jobs.managed_structure_prompt(
        "8a77d086-0b23-4a1e-89d0-f163fa23d5d1"
    )

    assert "langalpha-managed.md" in prompt
    assert "reading_a" in prompt
    assert "reading_b" in prompt
    assert "line_start" in prompt
    assert "line_end" in prompt
```

**Step 2: Run it to verify it fails**

Run: `uv run pytest tests/unit/server/services/test_education_structure_jobs.py -k reading_ranges -v`
Expected: FAIL.

**Step 3: Write the managed overlay**

`reference/langalpha-managed.md` states, in the same voice as the canonical
skill's own docs:

* read only `/managed/textbook-job/<job>/inputs/manifest.json`, `inputs/sources/` and staged assets;
* the caller already converted the PDF, so treat the staged Markdown as the source of truth and **do not** run any PDF extraction;
* produce exactly one candidate, `outputs/structure.json`, using the `langalpha-managed-textbook-structure/v2` shape below;
* boundaries are **line ranges into the source Markdown**, 1-based, inclusive `line_start` and exclusive `line_end`, computed from the actual file;
* granularity is Reading: every teaching Unit carries `reading_a` and `reading_b`, each with `title`, `line_start`, `line_end`, `summary`, `reading_skill`, `vocabulary_building`, `critical_thinking`;
* never invent a range you cannot derive from the file;
* all ranges for one Unit must sit inside the Unit's own range, and ranges must not overlap.

```json
{
  "format": "langalpha-managed-textbook-structure/v2",
  "units": [{
    "unit": 1,
    "theme": "Sports and Fitness",
    "line_start": 267,
    "line_end": 737,
    "readings": [{
      "slot": "reading_a",
      "title": "The World's Game",
      "line_start": 300,
      "line_end": 520,
      "summary": "...",
      "reading_skill": "Analyzing Infographics",
      "vocabulary_building": "Prefix uni-",
      "critical_thinking": "Evaluating Evidence"
    }]
  }]
}
```

**Step 4: Run the tests**

Run: `uv run pytest tests/unit/server/services/test_education_structure_jobs.py -q`
Expected: PASS.

**Step 5: Commit**

```bash
git add -A
git commit -m "feat(textbooks): managed reading-range prompt for canonical skill"
```

---

### Task 4: Validate and persist reading scopes

**Files:**
- Create: `src/server/services/education_structure_scope_validation.py`
- Modify: `src/server/services/education_structure_jobs.py` (`finalize_structure_generation`)
- Modify: `src/server/database/education_textbooks.py` (`replace_structure_contents`)
- Test: `tests/unit/server/services/test_education_structure_scope_validation.py`

**Step 1: Write the failing tests**

```python
def test_scope_validation_rejects_readings_that_escape_their_unit():
    payload = {
        "format": "langalpha-managed-textbook-structure/v2",
        "units": [{
            "unit": 1, "theme": "U", "line_start": 10, "line_end": 20,
            "readings": [{
                "slot": "reading_a", "title": "A",
                "line_start": 5, "line_end": 12,
            }],
        }],
    }
    with pytest.raises(ScopeValidationError):
        validate_structure_scopes(payload, source_line_count=100)


def test_scope_validation_rejects_overlapping_readings():
    ...


def test_scope_validation_accepts_a_well_formed_document():
    ...
```

**Step 2: Run them to verify they fail**

Run: `uv run pytest tests/unit/server/services/test_education_structure_scope_validation.py -v`
Expected: FAIL — the module does not exist.

**Step 3: Implement the validator**

Rules, all hard failures with actionable messages:

1. `format` is exactly `langalpha-managed-textbook-structure/v2`.
2. `1 <= line_start < line_end <= source_line_count` for Units and Readings.
3. A Reading range is contained by its parent Unit range.
4. Readings within a Unit do not overlap and are ordered.
5. Units do not overlap and are ordered.
6. Every teaching Unit has at least one Reading; `slot` is `reading_a` or `reading_b`.
7. A Reading's `title` is non-empty.

On success return the normalized payload plus, per Reading, the exact
`char_start` and `char_end` the import will persist.

**Step 4: Run the tests**

Run: `uv run pytest tests/unit/server/services/test_education_structure_scope_validation.py -q`
Expected: PASS.

**Step 5: Persist scopes**

Add one table and wire it through `replace_structure_contents`:

```sql
CREATE TABLE education_textbook_scopes (
    scope_id UUID PRIMARY KEY,
    structure_id UUID NOT NULL
        REFERENCES education_textbook_structures(structure_id)
        ON DELETE CASCADE,
    unit_id UUID NOT NULL
        REFERENCES education_structure_units(unit_id)
        ON DELETE CASCADE,
    slot VARCHAR(16) NOT NULL CHECK (slot IN ('reading_a', 'reading_b')),
    title TEXT NOT NULL,
    source_id TEXT NOT NULL,
    line_start INTEGER NOT NULL CHECK (line_start > 0),
    line_end INTEGER NOT NULL CHECK (line_end > line_start),
    char_start INTEGER NOT NULL CHECK (char_start >= 0),
    char_end INTEGER NOT NULL CHECK (char_end > char_start),
    summary TEXT NOT NULL DEFAULT '',
    UNIQUE (unit_id, slot)
);
```

**Step 6: Run the database and service suites**

Run: `uv run pytest tests/unit/server/database/test_education_structure_models.py tests/unit/server/services/test_education_structure_scope_validation.py -q`
Expected: PASS.

**Step 7: Commit**

```bash
git add -A
git commit -m "feat(textbooks): validate and persist reading scopes"
```

---

### Task 5: Delete the heuristic range inference

**Files:**
- Modify: `src/server/services/education_source_refs.py` (remove `locate_quote_approximately`, `resolve_quote_range`, `surrounding_section_range`, `locate_page_markers`)
- Modify: `src/server/services/education_structure_review.py` (`get_knowledge_point_source_preview`, `_locate_normalized_quote`)
- Modify: `src/server/services/education_lesson_jobs.py` (`build_lesson_source_context`)
- Delete: `tests/unit/server/services/test_education_source_refs.py`
- Modify: `tests/unit/server/services/test_education_lesson_jobs.py`
- Modify: `tests/unit/server/services/test_education_structure_review.py`

**Step 1: Write the failing test**

```python
def test_lesson_source_context_uses_only_the_reading_scope():
    scope = {
        "slot": "reading_b",
        "title": "What Makes an Olympic Champion?",
        "markdown": "...",
    }
    context, warnings = education_lesson_jobs.build_lesson_source_context(
        LESSON_JOB, FROZEN_INPUT, scopes=[scope]
    )

    assert warnings == []
    assert "What Makes an Olympic Champion?" in context
```

**Step 2: Run it to verify it fails**

Run: `uv run pytest tests/unit/server/services/test_education_lesson_jobs.py -k reading_scope -v`
Expected: FAIL — `build_lesson_source_context` takes two arguments.

**Step 3: Rewrite the consumers to require a scope**

`build_lesson_source_context(job, frozen_input, scopes)` concatenates the
chapter knowledge file and the source slice for the knowledge point's scope,
and raises `ValueError("Knowledge-point scope is unavailable")` when there is
none. No fallback slice, no approximate location, no padding.

**Step 4: Run the tests**

Run: `uv run pytest tests/unit/server/services -q`
Expected: PASS — the deleted helper tests are gone, the rewritten ones pass.

**Step 5: Prove the heuristics are gone**

Run: `rg -n "locate_quote_approximately|resolve_quote_range|surrounding_section_range|document_prefix|source_ref_approximate" src`
Expected: no matches.

**Step 6: Commit**

```bash
git add -A
git commit -m "refactor(textbooks): drop heuristic source-range inference"
```

---

### Task 6: Surface unverified scopes in the structure review UI

**Files:**
- Modify: `src/server/app/education/models.py`
- Modify: `src/server/app/education/textbooks.py`
- Modify: `web/src/pages/Education/types.ts`
- Modify: `web/src/pages/Education/TextbookStructurePage.tsx`
- Modify: `web/src/pages/Education/__tests__/TextbookStructurePage.test.tsx`

**Step 1: Write the failing test**

```tsx
it('flags a reading without a verified scope', () => {
  structureState.data = {
    ...structure,
    scopes: [{ slot: 'reading_a', verified: false }],
  };
  renderPage();

  expect(screen.getByTestId('scope-warning')).toHaveTextContent('范围待确认');
});
```

**Step 2: Run it to verify it fails**

Run: `cd web && pnpm vitest run src/pages/Education/__tests__/TextbookStructurePage.test.tsx -t scope`
Expected: FAIL.

**Step 3: Expose `scopes` on the structure response and render status**

Each scope carries `verified`, `line_start`, `line_end`, `char_start`,
`char_end` and the resolved `title`. A Reading whose scope failed validation is
shown with a warning badge, and its knowledge points cannot start lesson
generation.

**Step 4: Run the frontend suites**

Run: `cd web && pnpm vitest run src/pages/Education && pnpm typecheck`
Expected: PASS.

**Step 5: Commit**

```bash
git add -A
git commit -m "feat(textbooks): show reading scope verification in review UI"
```

---

### Task 7: Add the canonical generate pass and chapter import

**Files:**
- Create: `src/server/services/education_reading_assets.py`
- Modify: `src/server/services/education_structure_jobs.py`
- Modify: `src/server/services/education_teaching_storage.py`
- Test: `tests/unit/server/services/test_education_reading_assets.py`

**Step 1: Write the failing test**

```python
def test_reading_asset_staging_uses_the_scope_slice():
    files = build_reading_asset_inputs(job, frozen_input, scopes)

    assert files["inputs/readings/reading_a.md"].startswith(b"### THE WORLD'S GAME")
    assert b"SOCCER WITHOUT BORDERS" not in files["inputs/readings/reading_a.md"]
```

**Step 2: Run it to verify it fails**

Run: `uv run pytest tests/unit/server/services/test_education_reading_assets.py -v`
Expected: FAIL.

**Step 3: Implement the generate pass**

After the structure is accepted, one managed run per Reading:

* stage `inputs/readings/<slot>.md` = the deterministic slice;
* stage the chapter knowledge file as `inputs/chapters/<slot>-knowledge.md`;
* ask the canonical skill for `outputs/readings/<slot>.md` plus glossary and cheatsheet entries scoped to that Reading;
* store the result under `education/.../readings/<slot>/`.

**Step 4: Run the tests**

Run: `uv run pytest tests/unit/server/services/test_education_reading_assets.py -q`
Expected: PASS.

**Step 5: Commit**

```bash
git add -A
git commit -m "feat(textbooks): per-reading canonical generate pass"
```

---

### Task 8: Ground lessons in the scope and the chapter asset

**Files:**
- Modify: `src/server/services/education_lesson_jobs.py`
- Modify: `src/server/services/education_lesson_validation.py`
- Test: `tests/unit/server/services/test_education_lesson_jobs.py`

**Step 1: Write the failing test**

```python
def test_lesson_prompt_receives_chapter_file_and_source_slice():
    prompt = education_lesson_jobs.managed_lesson_prompt(
        LESSON_JOB, scope=READING_SCOPE, chapter_markdown="## Core Idea\n..."
    )

    assert "inputs/readings/reading_b.md" in prompt
    assert "inputs/chapters/reading_b-knowledge.md" in prompt
```

**Step 2: Run it to verify it fails**

Run: `uv run pytest tests/unit/server/services/test_education_lesson_jobs.py -k chapter_file -v`
Expected: FAIL.

**Step 3: Wire both inputs into lesson authoring**

The lesson prompt names both staged files, requires the lesson to stay inside
the Reading, and requires every quiz item to be answerable from the staged
slice. `education_lesson_validation` gains a check that the lesson Markdown
does not reference content outside its scope.

**Step 4: Run the tests**

Run: `uv run pytest tests/unit/server/services/test_education_lesson_jobs.py tests/unit/server/services/test_education_lesson_validation.py -q`
Expected: PASS.

**Step 5: Commit**

```bash
git add -A
git commit -m "feat(textbooks): ground lessons in reading scope and chapter assets"
```

---

### Task 9: Delete the legacy textbook data

**Files:**
- Create: `migrations/versions/075_reset_textbook_pipeline.py`
- Create: `scripts/education_purge_prefix.py`
- Test: `tests/unit/migrations/test_reset_textbook_pipeline.py`

**Step 1: Write the failing test**

```python
def test_reset_migration_clears_the_textbook_dependency_graph():
    source = Path("migrations/versions/075_reset_textbook_pipeline.py").read_text()

    assert "TRUNCATE TABLE education_textbooks" in source
    assert "RESTART IDENTITY CASCADE" in source
```

**Step 2: Run it to verify it fails**

Run: `uv run pytest tests/unit/migrations/test_reset_textbook_pipeline.py -v`
Expected: FAIL.

**Step 3: Write the reset migration**

The schema is already scope-aware after migrations 073 and 074, so truncate
the `education_textbooks` root with `CASCADE` instead of replaying the whole
textbook table graph. This removes every dependent version, structure, lesson,
assignment, progress and artifact-source row while leaving shared
`education_assets` untouched.

**Step 4: Purge the MinIO prefix**

```bash
uv run python scripts/education_purge_prefix.py \
  --prefix education/<household>/<textbook>/
uv run python scripts/education_purge_prefix.py \
  --prefix education/<household>/<textbook>/ --apply
```

The script requires one exact textbook prefix per `--prefix`. It touches only
versioned textbook keys below that prefix and its textbook `source-bundles/`;
shared homework attachments under `education/` are neither scanned nor deleted.

**Step 5: Run the migration tests**

Run: `uv run pytest tests/unit/migrations -q`
Expected: PASS.

**Step 6: Commit**

```bash
git add -A
git commit -m "feat(textbooks): reset textbook pipeline schema and data"
```

---

### Task 10: End-to-end verification on real data

**Files:**
- Create: `tests/integration/test_textbook_canonical_pipeline.py`
- Modify: `CHANGELOG.md`

**Step 1: Write the failing test**

```python
@pytest.mark.integration
async def test_pipeline_builds_scopes_from_real_markdown():
    structure = await run_analyze_pass(REAL_MARKDOWN)
    scopes = validate_structure_scopes(structure, source_line_count=6304)

    assert len(structure["units"]) == 12
    assert all(scope["char_end"] > scope["char_start"] for scope in scopes)
    assert scopes[0]["title"] == "The World's Game"
```

**Step 2: Run it to verify it fails**

Run: `uv run pytest -m integration tests/integration/test_textbook_canonical_pipeline.py -v`
Expected: FAIL until the pipeline is wired.

**Step 3: Run the pipeline against `doc-2spsb1AQdrRp`**

Generate the structure, accept it, generate one Reading's chapter file and one
lesson, and assert that the lesson cites the sliced source rather than outside
knowledge.

**Step 4: Verify manually in the app**

* structure review shows 12 Units with Reading A/B ranges;
* the evidence tab shows the exact slice for Reading B;
* a generated lesson stays inside the Reading.

**Step 5: Update `CHANGELOG.md` and commit**

```bash
git add -A
git commit -m "test(textbooks): verify canonical pipeline end to end"
```

---

## Verification checklist

* `uv run pytest tests/unit -q`
* `uv run pytest -m integration`
* `uv run ruff check src tests`
* `cd web && pnpm vitest run src/pages/Education && pnpm typecheck && pnpm build`
* `rg -n "the-knowledge-guy|locate_quote_approximately|surrounding_section_range" src` returns nothing
* structure review shows Reading-level ranges for all 12 Units
* a regenerated Reading B lesson cites only its own slice

## Rollback

The pre-migration state is tagged `v2026.09.21-pre-book-to-skill-redesign`.
Rolling back is a `git checkout` of that tag plus a database restore; the
schema reset in Task 9 is destructive and irreversible by design.
