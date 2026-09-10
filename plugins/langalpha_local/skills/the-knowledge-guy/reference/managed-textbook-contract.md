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
concept names exactly match its `knowledge_points`; every relation object uses
the literal `from_concept_id` and `to_concept_id` keys, never `from` or `to`,
and both values are existing same-chapter `concept_id` values; every practice
question uses an existing same-chapter `concept_id` and an exact knowledge
point. The book-wide concept index includes every verified concept and its
source chapter, and its relation objects use those same two literal keys for
concept IDs in that index.

`outputs/knowledge/concept-index.json` must use this exact top-level shape:

```json
{
  "format": "langalpha-managed-concept-index/v1",
  "concepts": [{
    "concept_id": "exact existing concept_id copied verbatim from a -knowledge.json",
    "name": "exact same concept name copied verbatim from that -knowledge.json",
    "content_chapter_ids": ["source content_chapter_id copied verbatim"]
  }],
  "relations": [{
    "from_concept_id": "an exact concept_id from concepts",
    "to_concept_id": "another exact concept_id from concepts",
    "type": "prerequisite"
  }]
}
```

The `concepts` array has every `concept_id` from every chapter `-knowledge.json`
exactly once. Copy each concept ID, name and source chapter ID verbatim from
that chapter knowledge asset. Do not rename, merge, substitute or add concepts.
Do not turn similarly named concepts into one cross-chapter item. The final
concept count equals the total number of concepts across the chapter knowledge
assets.

Each `-practice.json` uses this strict top-level shape:

```json
{
  "format": "langalpha-managed-chapter-practice/v1",
  "content_chapter_id": "frozen UUID",
  "content_sha256": "frozen 64-lowercase-hex",
  "questions": [{
    "position": 1,
    "concept_id": "same-chapter concept ID",
    "knowledge_point": "exact same-chapter knowledge point"
  }]
}
```

`questions` is a non-empty array. Do not use `exercises`, `items`, or another
replacement top-level field. Each question has a positive `position`, an exact
same-chapter `knowledge_point`, and a `concept_id` belonging to that chapter.

`outputs/knowledge/coverage-audit.json` must be strict JSON with this exact
top-level shape:

```json
{
  "format": "langalpha-managed-coverage-audit/v1",
  "chapters": [{
    "content_chapter_id": "frozen UUID",
    "content_sha256": "frozen 64-lowercase-hex",
    "status": "complete",
    "missing": [],
    "asset_kinds": ["knowledge", "toolkit", "practice", "teaching"]
  }]
}
```

The `chapters` array has exactly one item per frozen chapter. Do not use
`coverage`, `items`, or another substitute top-level field. Each chapter has
`status: "complete"`, `missing: []`, and `asset_kinds` equal to `knowledge`,
`toolkit`, `practice`, and `teaching` only when the actual outputs exist and
agree with that frozen chapter.

Use the teaching package to write substantial Chinese learning material: clear
objectives, prerequisite awareness, key difficulties, explanations calibrated
for Chinese learners, examples, misconceptions and auto-graded review
questions. It uses `langalpha-managed-teaching-package/v1` and must cover each
frozen chapter exactly once. Each chapter is strict JSON with this minimum
shape:

```json
{
  "content_chapter_id": "frozen UUID",
  "content_sha256": "frozen 64-lowercase-hex",
  "learning_objectives": ["Chinese objective"],
  "knowledge_points": ["exact Chinese knowledge point"],
  "key_difficulties": ["Chinese difficulty"],
  "prerequisites": ["optional prerequisite"],
  "teaching_material": "substantial Chinese explanation",
  "questions": [{
    "position": 1,
    "prompt": "question",
    "options": {"A": "option", "B": "option"},
    "correct_option": "A",
    "explanation": "Chinese explanation",
    "knowledge_point": "exact Chinese knowledge point"
  }]
}
```

Its chapter `knowledge_points` must exactly match the matching knowledge asset
list; every question `knowledge_point` must exactly match one of those strings.
Write strict JSON and escape inner double quotes in every JSON string.

Use only safe `EDUCATION_PROGRESS` stdout events after actual work. Allowed
phases are `planning`, `chapter_mapping`, `concept_linking`, `coverage_audit`,
`practice_build`, `teaching_build`, `bundle_assembling` and
`validating_bundle`; an event may mention only an allowed frozen chapter and
asset kind. Do not emit model reasoning, paths, object URLs, storage details,
provider data, credentials, counts or raw error text. The service performs the
final validation and private archive, so no output is published from this
environment.
