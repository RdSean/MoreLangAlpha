---
name: family-homework
description: Create text-only homework for a child in the caller's household
---

# Family Homework

Use this skill when a parent explicitly asks to assign homework or a learning
task to a child in their household.

## Workflow

1. Identify the child, subject, homework type, instructions, and due time.
2. Convert clear subject, type, and practice-source phrases to the stable
   dictionary codes expected by `education_create_homework`.
3. For relative times such as "明天晚上八点", use the caller's local or
   household timezone. Ask only for a missing or ambiguous value.
4. If multiple children have the same display name, ask the parent to choose
   one. Never guess a child from another household.
5. Call `education_create_homework` for a complete request. Do not claim that
   homework was created based on prose alone; report success only after the
   tool returns success.

The current phase accepts text instructions only. Do not upload, attach, or
pretend to associate images, PDFs, or chat files. Explain that attachments can
be handled from the education page when the parent asks for them.

Students cannot assign homework. A tool error is authoritative and must not be
worked around by asking for household IDs or parent IDs.
