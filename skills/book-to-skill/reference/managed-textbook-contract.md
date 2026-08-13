# Managed Textbook Contract

This contract is for the server-owned `--managed-textbook` mode only. It is
not a user-facing conversion workflow.

## Inputs and workspace

The service supplies only these staged files under one job root:

```text
/managed/textbook-job/<job>/inputs/manifest.json
/managed/textbook-job/<job>/inputs/chapters/<position>-<slug>.md
```

`manifest.json` contains a job identifier, frozen `content_chapter_id`, slug,
position and `content_sha256` for every chapter. The files contain extracted
Markdown. They contain no object-storage key, URL, credential or raw PDF.

The knowledge intermediate representation may be written only under:

```text
/managed/textbook-job/<job>/work/knowledge-skill/
```

The `book-to-skill` summary must be written to:

```text
/managed/textbook-job/<job>/outputs/book-skill-manifest.json
```

It includes the input manifest SHA-256, every `content_chapter_id` and
`content_sha256`, plus the skill generation version. It is intermediate only;
it is not a published asset.

## Teaching package schema

The second stage writes `outputs/teaching-package.json` with this shape:

```json
{
  "format": "langalpha-managed-teaching-package/v1",
  "chapters": [
    {
      "content_chapter_id": "uuid",
      "content_sha256": "64-lowercase-hex",
      "learning_objectives": ["..."],
      "knowledge_points": ["..."],
      "key_difficulties": ["..."],
      "prerequisites": ["..."],
      "teaching_material": "# Chinese teaching material",
      "questions": [
        {
          "position": 1,
          "prompt": "...",
          "options": {"A": "...", "B": "..."},
          "correct_option": "A",
          "explanation": "...",
          "knowledge_point": "..."
        }
      ]
    }
  ]
}
```

The service, rather than either Skill, validates chapter coverage, hashes,
limits, option counts, answers and knowledge-point links before writing any
official `education/` asset.
