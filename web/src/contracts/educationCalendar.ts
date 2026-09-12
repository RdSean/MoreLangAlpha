import { z } from 'zod';
import { educationTaskCalendarSchema } from './generated/educationCalendar.generated';

/**
 * The education calendar payload, as agreed by the backend and the frontend.
 *
 * The chain is Pydantic → JSON Schema → zod, each hop generated and each hop
 * guarded by a test that fails when the committed artifact goes stale:
 *
 *   src/server/app/education/models.py
 *     └─ scripts/contracts/export_schemas.py        → education-calendar.schema.json
 *     └─ web/scripts/generate-contracts.mjs         → generated/educationCalendar.generated.ts
 *
 * Do not hand-edit either generated file. Change the Pydantic model, re-run the
 * two generators, and this module follows.
 *
 * The schema is deliberately *structural*: `format` is stripped on the way out,
 * so it validates types, required fields, arrays and nullability, and leaves
 * date semantics alone. Accepting a `+09:00` offset is the point; accepting a
 * nonsense date string is the price. Both are pinned by tests.
 *
 * It is also non-strict about unknown keys, so a backend that adds a field does
 * not break an already-deployed client.
 */
export { educationTaskCalendarSchema };

export type EducationTaskCalendar = z.infer<typeof educationTaskCalendarSchema>;

/**
 * The nested shapes, so a caller that renders one day or one task does not have
 * to reach through the parent schema — or, worse, restate the shape by hand,
 * which is the duplication this contract exists to remove.
 *
 * Derived from the generated schema rather than converted separately, so the
 * three can never describe different versions of the same payload.
 */
export const educationCalendarDaySchema = educationTaskCalendarSchema.shape.days.element;

export const educationCalendarTaskSchema = educationCalendarDaySchema.shape.tasks.element;

export type EducationCalendarDay = z.infer<typeof educationCalendarDaySchema>;

export type EducationCalendarTask = z.infer<typeof educationCalendarTaskSchema>;

export type EducationCalendarStats = EducationTaskCalendar['stats'];
