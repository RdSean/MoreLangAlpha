# Native Book Learning Skills Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make `book-to-skill` and `the-knowledge-guy` discoverable and usable as project-native LangAlpha PTC skills, with generated book knowledge written under the existing `skills/` root.

**Architecture:** Keep the third-party skills project-local in `skills/` and record their source in `skills-lock.json`. Adapt their path instructions from Claude-specific directories to LangAlpha's `skills/` root, then register both skills explicitly in the static PTC skill registry. PyMuPDF remains an on-demand, isolated extractor dependency; no extraction setup or external provider integration runs during this work.

**Tech Stack:** Markdown skills, Python 3.13, pytest, Pydantic settings, LangAlpha PTC skill registry, skills.sh lockfile.

---

### Task 1: Lock the required native-skill contract

**Files:**
- Create: `tests/unit/middleware/skills/test_native_book_learning_skills.py`
- Modify: `tests/unit/middleware/skills/test_skill_registry.py`

**Step 1: Write failing registry and root-resolution tests.**

Assert that both `book-to-skill` and `the-knowledge-guy` are explicit PTC registry entries with the expected `skills/<name>/SKILL.md` path. Assert that both are included in PTC listings and the sandbox sync set, excluded from Flash, expose their slash-command shortcuts, and declare `skills/` as their primary project root.

**Step 2: Run the focused tests and confirm RED.**

Run:

```bash
uv run pytest tests/unit/middleware/skills/test_native_book_learning_skills.py tests/unit/middleware/skills/test_skill_registry.py -q
```

Expected: registry lookup fails because the two skills are not registered, and the path assertions fail because the imported instructions are Claude-specific.

### Task 2: Adapt book-skill instructions to the LangAlpha root

**Files:**
- Modify: `skills/book-to-skill/SKILL.md`
- Modify: `skills/the-knowledge-guy/SKILL.md`
- Modify: `skills/the-knowledge-guy/walk-mode.md`

**Step 1: Replace the book skill resolver with a root-aware version.**

Use `$(pwd)/skills/book-to-skill` as the first project-local location, followed by `$HOME/.ptc-agent/skills/book-to-skill`; keep Claude paths only as compatibility fallbacks. The resolver must test for `scripts/extract.py` before selecting a location.

**Step 2: Change generated-skill output and user messages to `skills/<slug>`.**

Set `SKILLS_ROOT="$(pwd)/skills"`, create `SKILL_DIR` beneath it, and update validation snippets and success output. Do not change the generated chapter schema, raw-text storage, audit process, course support, or the isolated extractor venv.

**Step 3: Make the knowledge router resolve its design assets and catalog from `skills/`.**

Define root-aware `TKG_DIR` and `SKILLS_ROOT` once near the top of `the-knowledge-guy/SKILL.md`; use those variables for design-system assets, book-skill discovery, practice discovery, and course rendering. Apply the same native root in `walk-mode.md`.

**Step 4: Keep the provider boundary explicit.**

Retain `scripts/setup.sh` and its isolated `uv` environment as the only place that installs PyMuPDF, ebooklib, BeautifulSoup, and pypdf. Add no dependency to `pyproject.toml` and make no Datalab call. The instruction should describe this as the current implementation behind a replaceable extraction contract.

### Task 3: Register the skills with the PTC runtime

**Files:**
- Modify: `src/ptc_agent/agent/middleware/skills/registry.py`

**Step 1: Add guidance-only PTC skill definitions.**

Add definitions matching the imported frontmatter and native paths:

```python
"book-to-skill": SkillDefinition(
    name="book-to-skill",
    description="Convert a PDF or EPUB into a project-local knowledge skill with chapter-level study material.",
    tools=[],
    skill_md_path="skills/book-to-skill/SKILL.md",
    exposure="ptc",
    command="book-to-skill",
),
"the-knowledge-guy": SkillDefinition(
    name="the-knowledge-guy",
    description="Teach from project book knowledge skills through question answering, guided walks, and course artifacts.",
    tools=[],
    skill_md_path="skills/the-knowledge-guy/SKILL.md",
    exposure="ptc",
    command="the-knowledge-guy",
),
```

Do not make either available to Flash in this change. Book extraction requires filesystem and sandbox work; the future student-facing Flash experience is a separate product feature.

**Step 2: Run the focused tests and confirm GREEN.**

Run the Task 1 command again. Confirm that both instructions parse with valid frontmatter, the registry resolves both names, commands map correctly, and sandbox sync selects the PTC-only skills.

### Task 4: Verify provenance and record the change

**Files:**
- Create: `skills-lock.json`
- Modify: `CHANGELOG.md`
- Modify: `skills/book-to-skill/**`
- Modify: `skills/the-knowledge-guy/**`

**Step 1: Inspect the skills.sh lockfile.**

Confirm that `skills-lock.json` pins `vitalysim/the-knowledge-guy` and the two selected skill names. Do not commit `.agents/skills/`, generated book content, the skill-local `.venv/`, or third-party installation caches.

**Step 2: Add a concise Chinese changelog entry.**

State that project-native book knowledge skills are available through PTC and generated book skills now use the project `skills/` root. State that PDF extraction dependencies remain on-demand and isolated.

**Step 3: Run verification.**

Run:

```bash
uv run pytest tests/unit/middleware/skills/test_native_book_learning_skills.py tests/unit/middleware/skills/test_skill_registry.py -q
uv run python -c 'from pathlib import Path; from src.ptc_agent.config.agent import SkillsConfig; assert Path(SkillsConfig().local_skill_dirs_with_sandbox(cwd=Path.cwd())[-1][0]).name == "skills"'
git diff --check
git status --short
```

Expected: focused tests pass, the PTC configuration resolves the project skills root, the diff has no whitespace errors, and only the planned files are staged.

**Step 4: Commit the completed integration.**

```bash
git add CHANGELOG.md skills-lock.json skills/book-to-skill skills/the-knowledge-guy src/ptc_agent/agent/middleware/skills/registry.py tests/unit/middleware/skills/test_native_book_learning_skills.py tests/unit/middleware/skills/test_skill_registry.py
git commit -m "feat(skills): add native book learning skills"
```

Do not stage `密码.md` or generated knowledge derived from a user's textbook.
