/**
 * GENERATED FILE — do not edit.
 *
 * Source: src/contracts/education-homework.schema.json
 * Produced by: web/scripts/generate-contracts.mjs
 * Which is fed by: scripts/contracts/export_schemas.py (from Pydantic)
 *
 * web/src/contracts/__tests__/generatedContracts.test.ts regenerates this and
 * fails if it is stale.
 */

import { z } from "zod"

export const educationHomeworkArtifactSchema = z.object({ "attachments_supported": z.boolean(), "destination": z.string().describe("Where the task can be seen, e.g. /education."), "due_at": z.string().describe("ISO 8601 due timestamp already converted to the household's timezone. A string rather than a datetime on purpose: Pydantic would re-serialise a datetime as UTC and quietly undo the household-local conversion."), "student_name": z.string().describe("Display name, resolved by the tool."), "success": z.boolean(), "task": z.object({ "assigned_student_id": z.string(), "completed_at": z.union([z.string(), z.null()]).default(null), "created_at": z.union([z.string(), z.null()]).default(null), "description": z.string(), "due_at": z.string(), "grade_code": z.union([z.string(), z.null()]).default(null), "household_id": z.string(), "latest_feedback_text": z.union([z.string(), z.null()]).default(null), "latest_review_decision": z.union([z.enum(["feedback","revision_requested"]), z.null()]).default(null), "occurrence_date": z.string(), "practice_source_code": z.union([z.string(), z.null()]).default(null), "status": z.string(), "subject_code": z.union([z.string(), z.null()]).default(null), "task_id": z.string(), "task_rule_id": z.string(), "title": z.string(), "type_code": z.union([z.string(), z.null()]).default(null) }).describe("The created task row as stored."), "task_id": z.string(), "type": z.literal("education_homework").default("education_homework") }).describe("What `education_create_homework` returns alongside its content.\n\nThis exists because the tool used to build its artifact as a raw dict: the\nfrontend dispatches on an artifact's ``type``, and a type that is not\npublished in ``web/src/contracts/artifact-types.json`` is a type no card\ncan be registered for — the transcript showed the tool step and nothing\nelse. Declaring the model here is what publishes it (see\n``scripts/contracts/export_schemas.py``), and the coverage test in\n``artifactIdCoverage.test.ts`` then refuses to let it render as a blank.")
