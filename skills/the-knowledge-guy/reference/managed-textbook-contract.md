# Managed Textbook Contract

This is the non-interactive `--managed-textbook` contract shared with
`book-to-skill`. It applies inside one service-owned PTC root, not to the
normal chat, course or HTML-artifact modes.

Read only the frozen Markdown and manifest under `inputs/` plus staged static
Skill documentation under `.agents/skills/`. The service has not supplied a
raw PDF, object storage, user memory, credentials, a network, or a general
workspace. PTC controls its own use of the two staged Skills and any permitted
internal reasoning; do not impose a second fixed service workflow.

Write only these service-derived candidate files:

```text
outputs/knowledge/concept-index.json
outputs/knowledge/coverage-audit.json
outputs/chapters/<position>-<slug>-knowledge.json
outputs/chapters/<position>-<slug>-toolkit.md
outputs/chapters/<position>-<slug>-practice.json
outputs/teaching-package.json
```

For every frozen chapter, the knowledge and practice JSON repeat its exact
`content_chapter_id` and `content_sha256`; the toolkit is Markdown. Knowledge
concept names exactly match its `knowledge_points`; every practice question
uses an existing same-chapter `concept_id` and an exact knowledge point. The
book-wide concept index includes every verified concept and its source chapter.
The coverage audit has every frozen chapter with `status: "complete"`,
`missing: []`, and `asset_kinds` equal to `knowledge`, `toolkit`, `practice`,
and `teaching`.

Use the teaching package to write substantial Chinese learning material: clear
objectives, prerequisite awareness, key difficulties, explanations calibrated
for Chinese learners, examples, misconceptions and auto-graded review
questions. It uses `langalpha-managed-teaching-package/v1` and must cover each
frozen chapter exactly once. Its chapter `knowledge_points` equal the matching
knowledge asset list; every question copies one of those strings verbatim.

Use only safe `EDUCATION_PROGRESS` stdout events after actual work. Allowed
phases are `planning`, `chapter_mapping`, `concept_linking`, `coverage_audit`,
`practice_build`, `teaching_build`, `bundle_assembling` and
`validating_bundle`; an event may mention only an allowed frozen chapter and
asset kind. Do not emit model reasoning, paths, object URLs, storage details,
provider data, credentials, counts or raw error text. The service performs the
final validation and private archive, so no output is published from this
environment.
