/**
 * GENERATED FILE — do not edit.
 *
 * Source: src/contracts/education-calendar.schema.json
 * Produced by: web/scripts/generate-contracts.mjs
 * Which is fed by: scripts/contracts/export_schemas.py (from Pydantic)
 *
 * web/src/contracts/__tests__/generatedContracts.test.ts regenerates this and
 * fails if it is stale.
 */

import { z } from "zod"

export const educationTaskCalendarSchema = z.object({ "days": z.array(z.object({ "completed_count": z.number().int(), "date": z.string(), "overdue_count": z.number().int(), "task_count": z.number().int(), "tasks": z.array(z.object({ "assigned_student_id": z.string(), "completed_at": z.union([z.string(), z.null()]).default(null), "created_at": z.union([z.string(), z.null()]).default(null), "description": z.string(), "due_at": z.string(), "grade_code": z.union([z.string(), z.null()]).default(null), "household_id": z.string(), "is_completed": z.boolean(), "is_overdue": z.boolean(), "occurrence_date": z.string(), "practice_source_code": z.union([z.string(), z.null()]).default(null), "status": z.string(), "subject_code": z.union([z.string(), z.null()]).default(null), "subject_color": z.union([z.string(), z.null()]).default(null), "task_id": z.string(), "task_rule_id": z.string(), "title": z.string(), "type_code": z.union([z.string(), z.null()]).default(null) })) })), "end_date": z.string(), "start_date": z.string(), "stats": z.object({ "completed_count": z.number().int(), "overdue_count": z.number().int(), "today_count": z.number().int(), "week_count": z.number().int() }), "student_id": z.union([z.string(), z.null()]).default(null) })
