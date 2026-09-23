# Knowledge-Point Lesson Generation Prompt Design

## Goal

Allow a parent to provide optional free-form guidance when generating a
knowledge-point lesson, so language, audience, structure, length, difficulty,
style and practice preferences are controllable without overriding the managed
lesson contract.

## Product Behavior

- The lesson generation and regeneration entry points share one optional
  "course generation requirements" input.
- The value is persisted with the generation job and restored when the page is
  reopened.
- The input is at most 4000 characters and defaults to empty.
- An active job with the same guidance may be reused.
- An active job with different guidance is a conflict. The user must cancel the
  active job before submitting a new prompt.
- The UI shows the guidance used by the active or latest job.

## Data Flow

1. Frontend sends `prompt` with `auto_grading`.
2. API normalizes the prompt and stores it in the existing
   `education_generation_jobs.processing_brief` column.
3. Lesson generation status returns the stored prompt.
4. Lesson launch reads the job prompt and passes it to
   `managed_lesson_prompt`.
5. The managed prompt appends a bounded user-guidance section with explicit
   precedence rules.

No migration is required because `processing_brief` already exists.

## Prompt Boundary

User guidance may control:

- language and target audience;
- lesson organization and section ordering;
- depth, length and difficulty;
- explanation and practice style;
- whether examples or summaries should be emphasized.

User guidance cannot override:

- the selected knowledge point and its frozen source material;
- source references and quote provenance;
- managed output paths and file formats;
- lesson or practice schemas;
- sandbox, credential, tool and security boundaries.

## Conflict Semantics

When the latest lesson job is active:

- identical normalized `(auto_grading, prompt)` is reused;
- different `auto_grading` or prompt raises
  `LessonGenerationConflictError` and maps to HTTP 409;
- no running job prompt is mutated.

## Frontend

- Add a textarea near the auto-grading control on the initial generation page.
- Add the same control to the existing lesson page next to regeneration.
- Prefill from `lessonGeneration.data.prompt`.
- Disable submission while a generation job is active.
- Show server conflict messages without silently discarding the entered prompt.

## Testing

- Request model rejects prompts over 4000 characters.
- Database queue reuses an active job only when prompt and auto-grading match.
- Different prompt returns a conflict and does not mutate the active job.
- Managed lesson prompt includes the guidance and precedence guard.
- API and status responses expose the persisted prompt.
- Frontend submits, restores, and displays the prompt.
