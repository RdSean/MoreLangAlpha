# Managed Textbook Contract

This contract is for the server-owned `--managed-textbook` mode only. It does
not run the normal interactive conversion workflow and it does not publish an
asset by itself.

## Managed textbook structure mode

When the service invokes `--managed-textbook-structure <job>`, the only allowed
output is:

```text
outputs/structure.json
```

The file uses `langalpha-managed-textbook-structure/v1`:

```json
{
  "format": "langalpha-managed-textbook-structure/v1",
  "units": [{
    "position": 1,
    "slug": "unit-1-sports",
    "title": "Unit 1: Sports and Fitness",
    "summary": "short summary",
    "unit_type": "teaching",
    "confidence": 0.96,
    "source_refs": [{
      "source_id": "source identity from manifest.json",
      "start": 0,
      "end": 500,
      "quote": "short source excerpt"
    }],
    "knowledge_points": []
  }]
}
```

`unit_type` is one of `teaching`, `front_matter`, `reference`, or `appendix`.
Every Unit must have at least one source reference. Every knowledge point must
have a title, confidence, and source reference. A non-teaching Unit must not invent knowledge points. A teaching Unit may have an empty knowledge-point list
until content supports a teachable point or until parent review adds one.

Do not generate lessons, practice files, teaching packages, HTML artifacts,
memory, or any path other than `outputs/structure.json`.

## Frozen inputs and capability boundary

The service supplies only these files under one job root:

```text
inputs/manifest.json
inputs/sources/<position>-<slug>.md
inputs/assets/<position>/<relative_path>
inputs/chapters/<position>-<slug>.md
.agents/skills/book-to-skill/
.agents/skills/the-knowledge-guy/
```

The manifest describes one or more complete source documents. Each source has
a frozen `content_chapter_id`, position, slug and `content_sha256`; the ID is
the existing output identity, not a claim that the source is a Unit. The parser
does not guarantee standard Unit/TOC boundaries. The manifest contains no
storage key, URL, credential, raw PDF, user memory or normal workspace state.
Read the staged Skill documentation only when it helps the task. The PTC root
decides its own map, reduce, audit and teaching order, and must generate the
final learning structure in the whitelisted outputs below; this contract does
not prescribe a service pipeline.

Referenced embedded images are staged under `inputs/assets/` only when the
source Markdown references them. Match them through each source's `asset_paths`
list; local Markdown image references may point to those staged asset paths.
Unreferenced assets are not supplied.

Only write the fixed candidate outputs below. Do not create other files, use
scripts, access a network, enumerate directories, or make public artifacts:

```text
outputs/knowledge/concept-index.json
outputs/knowledge/coverage-audit.json
outputs/chapters/<position>-<slug>-knowledge.json
outputs/chapters/<position>-<slug>-toolkit.md
outputs/chapters/<position>-<slug>-practice.json
outputs/teaching-package.json
```

Every frozen source must have exactly one `knowledge`, `toolkit` and
`practice` file. Use the literal position and slug from `manifest.json`; never
invent a path. Preserve the chapter ID and SHA-256 exactly in every chapter
JSON. The service downloads only these paths directly, then validates every
identity, reference and hash before it writes private `education/` assets.

## Chapter knowledge and toolkit

Each `-knowledge.json` has this minimum shape:

```json
{
  "format": "langalpha-managed-chapter-knowledge/v1",
  "content_chapter_id": "uuid",
  "content_sha256": "64-lowercase-hex",
  "knowledge_points": ["exact Chinese knowledge-point name"],
  "concepts": [{
    "concept_id": "stable-concept-id",
    "name": "exact Chinese knowledge-point name",
    "evidence": [{"start": 0, "end": 20}]
  }],
  "relations": [{
    "from_concept_id": "stable-concept-id",
    "to_concept_id": "another-stable-concept-id",
    "type": "prerequisite"
  }],
  "prerequisite_concept_ids": []
}
```

`concept_id` values are unique across the bundle. A concept name must equal a
same-chapter `knowledge_points` value. Evidence ranges point into that frozen
source Markdown; do not put a path, URL or quotation in them. Every relation
object must use the literal keys `from_concept_id` and `to_concept_id`, never
`from` or `to`, and both values must be same-chapter `concept_id` values. The
matching toolkit Markdown must contain learning objectives, key concepts,
common mistakes, a Chinese-learner explanation, an example and a chapter review
prompt.

## Complete-book knowledge assets

`outputs/knowledge/concept-index.json` has format
`langalpha-managed-concept-index/v1`. Its concepts exactly cover every chapter
concept and each item contains `concept_id`, identical `name`, and
`content_chapter_ids` containing its source chapter. Its relation objects also
use the literal `from_concept_id` and `to_concept_id` keys, and both values
must be concepts in that index.

Use this exact top-level shape:

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

`outputs/knowledge/coverage-audit.json` has format
`langalpha-managed-coverage-audit/v1` and must have this exact top-level
shape:

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

The `chapters` array has exactly one item per frozen source. Do not use
`coverage`, `items`, or another substitute top-level field. Do not report
complete coverage unless the actual outputs exist and agree with the frozen
chapter.

## Practice and Chinese teaching package

Each `-practice.json` has format
`langalpha-managed-chapter-practice/v1`, the exact chapter ID/hash, and
auto-graded questions. Its strict JSON top-level shape is:

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

`questions` must be a non-empty array. Do not use `exercises`, `items`, or
another replacement top-level field. Every question has a positive `position`,
an exact same-chapter `knowledge_point`, and a `concept_id` belonging to that
chapter.

`outputs/teaching-package.json` has format
`langalpha-managed-teaching-package/v1`. It contains every frozen chapter
exactly once. Each chapter is strict JSON with this minimum shape:

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

`content_chapter_id`, `content_sha256` and every question's
`knowledge_point` must exactly match the frozen input or its source
`knowledge_points`; that list must exactly match the corresponding knowledge
asset's list. Write strict JSON and escape inner double quotes in every JSON
string.

After a real completed unit, emit at most one `EDUCATION_PROGRESS ` stdout
line with JSON containing only `phase`, optional frozen `content_chapter_id`,
and optional asset kind. Allowed phases are `planning`, `chapter_mapping`,
`concept_linking`, `coverage_audit`, `practice_build`, `teaching_build`,
`bundle_assembling` and `validating_bundle`. Never emit free model reasoning,
paths, URLs, credentials, provider text or self-reported totals.
