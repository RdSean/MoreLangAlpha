# Managed Textbook Contract

This is the non-interactive `--managed-textbook` contract shared with
`book-to-skill`. The process receives only:

```text
/managed/textbook-job/<job>/inputs/manifest.json
/managed/textbook-job/<job>/inputs/chapters/<position>-<slug>.md
/managed/textbook-job/<job>/work/knowledge-skill/
```

It writes exactly one candidate to:

```text
/managed/textbook-job/<job>/outputs/teaching-package.json
```

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

Each completed chapter emits one stdout line prefixed with
`EDUCATION_PROGRESS ` followed by JSON containing `content_chapter_id` and
`phase`. The service validates all `content_chapter_id`, `content_sha256`,
`learning_objectives`, `knowledge_points`, `teaching_material`, questions and
`correct_option` values before publication. No storage key, object URL,
credential, user memory, artifact or chat transcript is accepted or emitted.

Every question's `knowledge_point` must exactly match one string in its own
chapter's `knowledge_points`; copy that string without expanding or rephrasing
it.
