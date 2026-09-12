import { describe, expect, it } from 'vitest';
import wire from './__fixtures__/education-calendar.wire.json';
import {
  educationCalendarTaskSchema,
  educationTaskCalendarSchema,
  type EducationCalendarTask,
} from '../educationCalendar';

/**
 * The fixture is a payload captured from the real service, serialised the way
 * FastAPI serialises a `response_model` (`model_dump(mode="json")`) — see the
 * design doc for why `json.dumps(default=str)` produces a *different* shape and
 * would make this suite lie. Household and task identifiers were replaced with
 * stable stand-ins; every date, clock time, title and nullability is as the
 * wire produced it, because those are what the contract is about.
 */
const payload = wire as unknown as Record<string, unknown>;

function clone(): Record<string, unknown> {
  return structuredClone(payload);
}

function firstTask(target: Record<string, unknown>): Record<string, unknown> {
  const days = target.days as Array<{ tasks: Record<string, unknown>[] }>;
  return days[0].tasks[0];
}

describe('generated education calendar contract', () => {
  it('accepts the real wire payload', () => {
    const result = educationTaskCalendarSchema.safeParse(payload);
    expect(result.success, JSON.stringify(result.error?.issues?.[0] ?? {})).toBe(true);
  });

  it('rejects a payload missing a required field', () => {
    const broken = clone();
    delete broken.stats;
    expect(educationTaskCalendarSchema.safeParse(broken).success).toBe(false);
  });

  it('rejects a wrong type and points at the offending task', () => {
    const broken = clone();
    firstTask(broken).is_overdue = 'yes';

    const result = educationTaskCalendarSchema.safeParse(broken);
    expect(result.success).toBe(false);
    const path = result.error!.issues[0].path.join('.');
    expect(path).toContain('days.0.tasks.0');
    expect(path).toContain('is_overdue');
  });

  it('accepts an unknown extra key (a boundary check, not a strict gate)', () => {
    // A backend that adds a field must not break an older client mid-deploy.
    const extended = clone();
    extended.something_new = { added_by: 'a later backend' };
    expect(educationTaskCalendarSchema.safeParse(extended).success).toBe(true);
  });

  it('exposes the nested task shape for callers that need only that', () => {
    const task = firstTask(clone());
    const result = educationCalendarTaskSchema.safeParse(task);
    expect(result.success).toBe(true);
    const typed: EducationCalendarTask = result.data as EducationCalendarTask;
    expect(typeof typed.title).toBe('string');
    expect(typeof typed.is_overdue).toBe('boolean');
  });

  it('rejects a task whose nested shape is wrong when used on its own', () => {
    const task = firstTask(clone());
    task.occurrence_date = 42;
    expect(educationCalendarTaskSchema.safeParse(task).success).toBe(false);
  });

  // ---------------------------------------------------------------------------
  // Why `format` is stripped from the generated schema
  // ---------------------------------------------------------------------------

  it('accepts a non-UTC offset in a datetime field', () => {
    // The reason the exporter drops `format`: zod's JSON-Schema-derived
    // `date-time` validator accepts only a `Z` suffix, so this valid ISO 8601
    // value — what a household east of UTC produces — would be rejected.
    const offset = clone();
    firstTask(offset).due_at = '2026-09-13T19:00:00+09:00';
    expect(educationTaskCalendarSchema.safeParse(offset).success).toBe(true);
  });

  it('deliberately does not validate date semantics', () => {
    // The other half of that trade: the contract checks structure, not dates.
    // Pinned here so nobody assumes a parsed payload has sane dates in it.
    const nonsense = clone();
    firstTask(nonsense).due_at = 'not-a-date';
    expect(educationTaskCalendarSchema.safeParse(nonsense).success).toBe(true);
  });
});
