# LangAlpha managed mode

This file is not part of the upstream skill. It describes the service-owned
managed job that LangAlpha runs, and overrides the interactive defaults in
`SKILL.md` for that job only.

## When this mode applies

The invocation names a managed job root of the form
`/managed/textbook-job/<uuid>/`. In that case:

* Read only `<root>/inputs/manifest.json`, `<root>/inputs/sources/`,
  `<root>/inputs/assets/` and the staged skill directory
  `<root>/.agents/skills/book-to-skill/`.
* The caller has already converted the source document to high-fidelity
  Markdown. **Do not run any PDF, EPUB, DOCX or Calibre extraction.** The
  staged Markdown is the source of truth.
* Do not ask the user anything. Do not browse, use MCP, or write outside the
  job root.

## Analyze pass (Steps 0–3 of the skill)

Write exactly one candidate:

```
<root>/outputs/structure.json
```

Use `langalpha-managed-textbook-structure/v2`:

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
      "summary": "one paragraph, in the source language",
      "reading_skill": "Analyzing Infographics",
      "vocabulary_building": "Prefix uni-",
      "critical_thinking": "Evaluating Evidence"
    }, {
      "slot": "reading_b",
      "title": "What Makes an Olympic Champion?",
      "line_start": 521,
      "line_end": 700,
      "summary": "…",
      "reading_skill": "Scanning for Specific Information",
      "vocabulary_building": "Suffix -ology",
      "critical_thinking": "Evaluating Reasons"
    }]
  }]
}
```

### Boundary rules — these are the point of this mode

* `line_start` and `line_end` are **1-based line numbers into the staged
  Markdown source**, counted from the actual file.
* `line_start` is inclusive, `line_end` is exclusive.
* The granularity is the **Reading**, not the whole Unit. A Unit that contains
  Reading A and Reading B must produce one `readings[]` entry per Reading.
* A Reading range must sit entirely inside its parent Unit range.
* Ranges must not overlap, and Units must appear in reading order.
* Derive each boundary from a real structural landmark in the file — a Unit or
  Reading heading, a page marker, or the exercise block that closes the
  Reading. Do not estimate a boundary you cannot point at.
* Open a Reading at its first content line (the warm-up or `BEFORE YOU READ`
  block that belongs to it) and close it after that Reading's own vocabulary or
  critical-thinking practice, before the next Reading or the video block.
* A unit with front matter, contents, references or an appendix is not a
  teaching Unit. Emit it only if the book actually contains such a block.

### Fields

* `slot` is `reading_a` or `reading_b`.
* `title` is the reading's own title, taken from the source.
* `summary` is one short paragraph describing what the Reading teaches.
* `reading_skill`, `vocabulary_building` and `critical_thinking` name the
  Reading's skill strands when the book has them. Omit a field rather than
  inventing a value.
* Do not emit `position`, `slug`, character offsets or PDF page numbers; the
  service derives those from the line ranges.

## Lesson and asset passes

Those passes are described by the caller's own prompt. They consume the line
ranges produced here and must not re-derive boundaries.
