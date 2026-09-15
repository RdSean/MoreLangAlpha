import { z } from 'zod';
import { educationHomeworkArtifactSchema } from './generated/educationHomework.generated';

/**
 * The artifact `education_create_homework` returns, as agreed by both sides.
 *
 * Same chain as the other two contracts: Pydantic → JSON Schema → zod, each hop
 * generated and each hop guarded by a test that fails when the committed file
 * goes stale. Change `src/tools/education/schemas.py`, run `make contracts`,
 * and this follows.
 *
 * The tool used to hand the transcript a raw dict with no published type, so
 * the card that renders a created task could not exist: the artifact arrived,
 * no renderer claimed it, and the message ended at the tool step.
 */
export { educationHomeworkArtifactSchema };

export type EducationHomeworkArtifact = z.infer<typeof educationHomeworkArtifactSchema>;

/** The created task row, for a card that shows what was actually stored. */
export const educationHomeworkTaskSchema = educationHomeworkArtifactSchema.shape.task;

export type EducationHomeworkTask = z.infer<typeof educationHomeworkTaskSchema>;
