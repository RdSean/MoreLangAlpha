import { z } from 'zod';
import { homeworkScheduleArtifactSchema } from './generated/homeworkSchedule.generated';

/**
 * The homework artifact the agent tool returns, as agreed by both sides.
 *
 * Same chain as `educationCalendar.ts`: Pydantic → JSON Schema → zod, each hop
 * generated and each hop guarded by a test that fails when the committed
 * artifact goes stale. Change `src/tools/homework/schemas.py`, run the two
 * generators, and this follows.
 *
 * The artifact embeds the calendar API's own day and task models, so a task
 * parsed here and a task parsed from `educationCalendar.ts` describe the same
 * thing — the reuse is what keeps the chat card and the dashboard widget from
 * drifting apart.
 */
export { homeworkScheduleArtifactSchema };

export type HomeworkScheduleArtifact = z.infer<typeof homeworkScheduleArtifactSchema>;

/** The embedded day and task shapes, for a card that renders one of them. */
export const homeworkScheduleDaySchema = homeworkScheduleArtifactSchema.shape.days.element;

export const homeworkScheduleTaskSchema = homeworkScheduleDaySchema.shape.tasks.element;

export type HomeworkScheduleDay = z.infer<typeof homeworkScheduleDaySchema>;

export type HomeworkScheduleTask = z.infer<typeof homeworkScheduleTaskSchema>;

export type HomeworkScheduleStats = HomeworkScheduleArtifact['stats'];
