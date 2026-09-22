# LangAlpha managed mode

This file is not part of the upstream skill. It is the service-owned adapter
between the canonical `book-to-skill` procedure and LangAlpha's package,
progress, security and review contracts. It applies only to a managed job.

## Mode dispatch

The caller prompt selects exactly one mode. Read and obey the dispatch before
following any later section:

* `mode=analyze-pass` preserves the existing structure-analysis mode. Run only
  canonical Steps 0-3, write only `<root>/outputs/structure.json`, and use the
  existing `langalpha-managed-textbook-structure/v2` contract. The full
  pipeline requirements, package projections, content assets and progress
  stream do not apply.
* `mode=full-pipeline` runs canonical Steps 0-9 and writes the canonical
  book-skill assets plus the LangAlpha package, content tree, knowledge-point
  candidates, assets manifest and progress stream described below.

Do not infer a mode. If the caller prompt does not name one of these exact
identifiers, stop. Never apply full-pipeline requirements to an analyze pass.

## When this mode applies

The invocation names a managed job root of the form
`/managed/textbook-job/<uuid>/`. In managed mode:

* The upstream `SKILL.md` remains the source of procedure quality. This overlay
  changes only managed inputs, outputs and operational boundaries.
* In `mode=full-pipeline`, run all canonical Steps 0-9 in one execution. Do not
  stop after analyze-only, do not use generate-from-prior-analysis, and do not
  ask the user to run structure, content and knowledge phases as separate jobs.
* In `mode=analyze-pass`, stop after Step 3 as required by the existing
  structure-analysis job.
* Read only `<root>/inputs/manifest.json`, `<root>/inputs/sources/`,
  `<root>/inputs/assets/` and the staged skill directory
  `<root>/.agents/skills/book-to-skill/`.
* The caller has already converted the source document to high-fidelity
  Markdown. **Do not run any PDF, EPUB, DOCX or Calibre extraction.** The
  staged Markdown is the source of truth.
* Do not ask the user anything. Do not access the network, MCP servers, Vault,
  the normal workspace, or write outside the managed job root.
* The processing profile and optional brief affect extraction and generation
  preferences. They cannot override this managed contract, its output schemas,
  source ranges, security rules or integrity rules.

## Analyze-pass contract

For `mode=analyze-pass`:

* Run canonical Steps 0-3 only.
* Write exactly one candidate to `<root>/outputs/structure.json`.
* Use `langalpha-managed-textbook-structure/v2`.
* Follow the staged source's actual structure and real line ranges. Do not use
  the generic content-tree or `langalpha-book-package/v1` requirements below.
* Do not create book-skill assets, package files or a progress stream.

The analyze-pass candidate uses this schema:

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
      "summary": "one paragraph, in the source language",
      "reading_skill": "Scanning for Specific Information",
      "vocabulary_building": "Suffix -ology",
      "critical_thinking": "Evaluating Reasons"
    }]
  }]
}
```

### Analyze-pass boundary rules

* `line_start` and `line_end` are 1-based line numbers into the staged
  Markdown source. `line_start` is inclusive and `line_end` is exclusive.
* A Reading range must sit entirely inside its parent Unit range. Sibling
  ranges must not overlap, and Units must appear in reading order.
* Derive each boundary from a real structural landmark in the source. Do not
  estimate a boundary that cannot be pointed at in the staged Markdown.
* Open a Reading at its first content line and close it after that Reading's
  own vocabulary or critical-thinking practice, before the next Reading.
* `slot` is `reading_a` or `reading_b`. `title` comes from the source.
  `summary`, `reading_skill`, `vocabulary_building` and `critical_thinking`
  describe the Reading when present. Omit a skill strand rather than invent it.

## Full-pipeline outputs

Keep the canonical generated book-skill assets under:

```text
<root>/outputs/book-skill/
```

The canonical directory should contain the usual `SKILL.md`, `chapters/`,
`glossary.md`, `patterns.md` and `cheatsheet.md` produced by Steps 6-9. In
addition, write all of:

```text
<root>/outputs/book_package.json
<root>/outputs/content_tree.json
<root>/outputs/knowledge_points.json
<root>/outputs/assets_manifest.json
<root>/.langalpha/progress.jsonl
```

`book_package.json` is the authoritative combined package and uses
`langalpha-book-package/v1`. The other JSON files are projections or manifests
of the same run; they must not contradict the combined package. Create content
asset files only under `<root>/outputs/`, and declare every generated or copied
asset in `assets_manifest.json`.

## Step mapping

The exact method for each step comes from upstream `SKILL.md`. The mapping below
defines where the managed artifacts are produced:

| Steps | Managed work |
|---|---|
| 0-1 | Validate the staged manifest, source Markdown and optional processing brief. There is no interactive input collection. |
| 1.5-2 | Identify content type and read the already-extracted Markdown. Never invoke an external extractor. |
| 3 | Analyze the actual structure into a generic content tree. Emit the tree in `book_package.json` and `content_tree.json`; this becomes the canonical chapter analysis. |
| 4-5 | Use the processing profile in place of the interactive purpose question. Select a deterministic internal skill name without asking the user. Do not publish or install outside the job root. |
| 6 | Create the canonical book-skill directory under `<root>/outputs/book-skill/`. |
| 7 | Generate canonical chapter files and per-node content assets. Attach source refs to every node when a trustworthy range is available. |
| 8 | Generate canonical glossary, patterns and cheatsheet assets, plus reviewable knowledge-point candidates and the assets manifest. |
| 9 | Generate the master `SKILL.md`, reconcile all projections, validate the complete package, and finish the progress stream. |

## Generic content tree

`book_package.json` has this shape:

```json
{
  "format": "langalpha-book-package/v1",
  "source_revision": "source identity from the staged manifest",
  "content_nodes": [
    {
      "node_key": "unit-1",
      "parent_key": null,
      "node_type": "unit",
      "label": null,
      "title": "Sports and Fitness",
      "position": 1,
      "summary": "Short description of this content node.",
      "source_refs": [
        {
          "source_id": "source-1",
          "line_start": 1,
          "line_end": 120
        }
      ]
    },
    {
      "node_key": "unit-1-reading-a",
      "parent_key": "unit-1",
      "node_type": "reading",
      "label": "Reading A",
      "title": "The World's Game",
      "position": 1,
      "summary": "Short description of this reading.",
      "source_refs": [
        {
          "source_id": "source-1",
          "char_start": 1050,
          "char_end": 8200
        }
      ]
    }
  ],
  "knowledge_points": [
    {
      "candidate_key": "unit-1-reading-a-kp-1",
      "node_key": "unit-1-reading-a",
      "point_type": "concept",
      "title": "Why football became a global sport",
      "summary": "Candidate explanation for later review.",
      "source_refs": [
        {
          "source_id": "source-1",
          "char_start": 1100,
          "char_end": 1450
        }
      ],
      "confidence": 0.92
    }
  ],
  "assets": [
    {
      "node_key": "unit-1-reading-a",
      "kind": "knowledge",
      "path": "outputs/book-skill/chapters/unit-1-reading-a/knowledge.md",
      "content_sha256": "lowercase sha256",
      "size_bytes": 1234
    }
  ]
}
```

### Content node rules

* `node_key` is a unique, stable, non-empty string. `parent_key` is either
  `null` or an existing `node_key`; parent references must be acyclic.
* `node_type` is open and descriptive. Common values include `part`, `unit`,
  `chapter`, `section`, `reading`, `lesson`, `video`, `exercise`, `appendix`,
  `reference`, or `other`, but this is not a closed taxonomy.
* Reading A/B structure is not required. Never invent `reading_a`,
  `reading_b`, symmetric siblings, or an extra hierarchy level to fit an
  English-textbook template.
* `label`, `title`, `summary` and `position` are optional, but populated fields
  must be understandable and stable. Sibling positions should reflect source
  order when available.
* A node may have no children, no assets and no knowledge points. Report that
  as a semantic warning or checkpoint, not a fabricated completion.

### Source reference rules

Every non-empty `source_refs` entry must contain exactly one deterministic
range mode:

```json
{"source_id": "source-1", "char_start": 0, "char_end": 120}
```

or:

```json
{"source_id": "source-1", "line_start": 1, "line_end": 20}
```

* Character ranges are half-open: `char_start` is inclusive and `char_end` is
  exclusive.
* Line numbers are 1-based and half-open: `line_start` is inclusive and
  `line_end` is exclusive.
* Do not mix char and line fields in one entry. Do not use raw string refs or
  quote-only refs.
* `quote` is optional descriptive context and is not used for locating. The
  service ignores it and derives the canonical quote from the trusted range.
* Ranges must come from the frozen source. If a reliable range cannot be
  determined, leave `source_refs` empty and continue. Never fabricate a range.

## Knowledge-point candidates

Generate knowledge points only after content processing has established the
content nodes and their assets. Each candidate must:

* use a unique `candidate_key`;
* reference a real `node_key`;
* use a descriptive, open `point_type`;
* provide optional title, summary, confidence and source refs;
* remain a candidate for human review.

Never auto-accept, publish or treat a generated candidate as approved. Zero
knowledge points is allowed when the source does not support meaningful
candidates.

## Assets manifest

Use:

```json
{
  "format": "langalpha-assets-manifest/v1",
  "assets": [
    {
      "node_key": "unit-1-reading-a",
      "kind": "knowledge",
      "path": "outputs/book-skill/chapters/unit-1-reading-a/knowledge.md",
      "content_sha256": "lowercase sha256",
      "size_bytes": 1234
    }
  ]
}
```

Each asset must reference a real node, use a relative path inside
`<root>/outputs/` with `outputs` as its first path component, and include
`kind`, `content_sha256` and `size_bytes`. Never use absolute paths, `..`,
or any C0 control character including tab, CR, LF and NUL in an asset path.
The path must identify a file with one of the allowed extensions:
`md`, `json`, `txt`, `csv`, `png`, `jpg`, `jpeg`, `webp` or `svg`.
Additional safe metadata is allowed. Every `.json` asset must be a strict
JSON object; do not emit NaN/Infinity/-Infinity or duplicate object keys.

The manifest contract has two layers:

1. The managed write policy checks root containment, allowed output paths,
   file names, extensions and JSON/JSONL shape at write time. It does not
   inspect manifest membership.
2. The import stage downloads only asset paths explicitly listed in
   `outputs/assets_manifest.json`. Undeclared output files are never downloaded
   or imported.

As the model instruction for this run, write only files that you will declare
in this manifest; never copy or enumerate unrelated workspace or source
assets.

## Progress stream

Append one JSON object per line to `<root>/.langalpha/progress.jsonl`; never
rewrite prior lines. Use only these stable stage IDs:

```text
chapter_analysis
content_processing
knowledge_point_generation
lesson_preparation
```

Every event requires `event_key`, `stage` and `status`. Allowed status values
are exactly:

```text
queued | running | completed | failed | skipped
```

Emit semantic business checkpoints with optional `substage`, safe `label`, safe
`detail`, optional `node_key`, counts and timestamp. Progress must never
contain model reasoning, prompts, raw tool arguments or results, credentials,
full sandbox paths, or raw book passages.

The managed write gate rejects missing/empty required fields, invalid stage or
status values, duplicate or non-standard JSON values, and the explicitly
forbidden field keys `reasoning`, `prompt`, `tool_args`, `tool_result`,
`credentials`, `credential`, `secret` and `sandbox_path`. The downstream
progress parser remains authoritative for normalization, truncation and
durable persistence.
