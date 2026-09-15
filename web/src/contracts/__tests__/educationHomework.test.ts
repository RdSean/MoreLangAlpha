import { describe, expect, it } from 'vitest';
import artifactFixture from './__fixtures__/education-homework.wire.json';
import {
  educationHomeworkArtifactSchema,
  educationHomeworkTaskSchema,
} from '../educationHomework';

/**
 * The fixture is a real artifact: built from the same service the tool calls,
 * serialised with `model_dump(mode="json")`, with household/student identifiers
 * and the child's name replaced by stable stand-ins. Dates, titles and
 * nullability are exactly as the wire produced them.
 */
const payload = artifactFixture as unknown as Record<string, unknown>;

function clone(): Record<string, unknown> {
  return structuredClone(payload);
}

describe('generated education homework artifact contract', () => {
  it('accepts the real artifact', () => {
    const result = educationHomeworkArtifactSchema.safeParse(payload);
    expect(result.success, JSON.stringify(result.error?.issues?.[0] ?? {})).toBe(true);
  });

  it('carries the discriminator the card dispatches on', () => {
    const wrong = clone();
    wrong.type = 'homework_schedule';
    expect(educationHomeworkArtifactSchema.safeParse(wrong).success).toBe(false);
  });

  it('keeps the due time as the household-local string the tool sent', () => {
    // A datetime here would be re-serialised as UTC by Pydantic and quietly
    // move the deadline the parent was told about.
    expect(payload.due_at).toBe('2026-09-16T18:00:00+09:00');
  });

  it('describes the stored task, so the card can show what was created', () => {
    const task = educationHomeworkTaskSchema.safeParse(payload.task);
    expect(task.success, JSON.stringify(task.error?.issues?.[0] ?? {})).toBe(true);
    if (task.success) {
      expect(task.data.title.length).toBeGreaterThan(0);
      expect(task.data.status).toBeTruthy();
    }
  });

  it('rejects a payload with no task behind it', () => {
    const broken = clone();
    delete broken.task;
    expect(educationHomeworkArtifactSchema.safeParse(broken).success).toBe(false);
  });
});
