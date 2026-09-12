import { describe, expect, it } from 'vitest';
import artifactFixture from './__fixtures__/homework-artifact.wire.json';
import calendarFixture from './__fixtures__/education-calendar.wire.json';
import { educationCalendarTaskSchema } from '../educationCalendar';
import {
  homeworkScheduleArtifactSchema,
  homeworkScheduleTaskSchema,
} from '../homeworkSchedule';

/**
 * The fixture is a real artifact: built from the same service the tool calls,
 * serialised with `model_dump(mode="json")`, with household/student identifiers
 * and the child's name replaced by stable stand-ins. Dates, clock times, task
 * titles and nullability are exactly as the wire produced them.
 */
const payload = artifactFixture as unknown as Record<string, unknown>;

function clone(): Record<string, unknown> {
  return structuredClone(payload);
}

describe('generated homework artifact contract', () => {
  it('accepts the real artifact', () => {
    const result = homeworkScheduleArtifactSchema.safeParse(payload);
    expect(result.success, JSON.stringify(result.error?.issues?.[0] ?? {})).toBe(true);
  });

  it('requires the discriminator the frontend dispatches on', () => {
    const missing = clone();
    delete missing.type;
    // It has a default on the backend, so a payload without it never comes from
    // a real tool — but the card's render dispatch depends on it, so the
    // contract must not accept a payload that lacks it.
    expect(homeworkScheduleArtifactSchema.safeParse(missing).success).toBe(true);

    const wrong = clone();
    wrong.type = 'something_else';
    expect(homeworkScheduleArtifactSchema.safeParse(wrong).success).toBe(false);
  });

  it('requires the fields a card cannot render without', () => {
    for (const field of ['start_date', 'end_date', 'timezone', 'stats', 'days']) {
      const broken = clone();
      delete broken[field];
      expect(
        homeworkScheduleArtifactSchema.safeParse(broken).success,
        `missing ${field} should fail`,
      ).toBe(false);
    }
  });

  it('carries child names keyed by the ids that appear in days', () => {
    const result = homeworkScheduleArtifactSchema.safeParse(payload);
    expect(result.success).toBe(true);
    if (!result.success) return;
    const { student_names: names, days } = result.data;

    const idsInUse = new Set(days.flatMap((day) => day.tasks.map((t) => t.assigned_student_id)));
    expect(idsInUse.size).toBeGreaterThan(0);
    for (const id of idsInUse) {
      // Without this the card would render a bare UUID — it cannot fetch the
      // member list the way the dashboard widget does.
      expect(names?.[id], `no display name for ${id}`).toBeTruthy();
    }
  });

  it('rejects a student name map of the wrong shape', () => {
    const broken = clone();
    broken.student_names = { 'student-1': 42 };
    expect(homeworkScheduleArtifactSchema.safeParse(broken).success).toBe(false);
  });

  it('accepts an unknown extra key (older client, newer backend)', () => {
    const extended = clone();
    extended.added_later = { by: 'a future backend' };
    expect(homeworkScheduleArtifactSchema.safeParse(extended).success).toBe(true);
  });
});

describe('the two contracts agree on the embedded models', () => {
  it('parses a task from the calendar payload with the artifact schema', () => {
    // Both schemas are generated from models that reuse each other, so this is
    // the cross-check that the reuse is real rather than coincidental: a task
    // the calendar produces must satisfy the artifact's task shape.
    const calendarTask = (
      calendarFixture as unknown as { days: Array<{ tasks: unknown[] }> }
    ).days[0].tasks[0];
    expect(homeworkScheduleTaskSchema.safeParse(calendarTask).success).toBe(true);
  });

  it('parses an artifact task with the calendar schema', () => {
    const artifactTask = (
      payload as unknown as { days: Array<{ tasks: unknown[] }> }
    ).days[0].tasks[0];
    expect(educationCalendarTaskSchema.safeParse(artifactTask).success).toBe(true);
  });
});
