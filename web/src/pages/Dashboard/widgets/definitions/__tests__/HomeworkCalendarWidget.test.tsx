import { fireEvent, render, screen, within } from '@testing-library/react';
import { useState } from 'react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import en from '@/locales/en-US.json';

const state = vi.hoisted(() => ({
  isLoading: false,
  calendar: null as Record<string, unknown> | null,
  members: [] as Array<{ user_id: string; name: string; role: 'parent' | 'student' }>,
  calls: [] as Array<Record<string, unknown>>,
  membersEnabled: [] as boolean[],
}));

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({ member: { user_id: 'parent-1', role: 'parent' } }),
}));

vi.mock('@/pages/Education/queries', () => ({
  useEducationTaskCalendar: (params: Record<string, unknown>) => {
    state.calls.push(params ?? {});
    return { data: state.calendar, isLoading: state.isLoading };
  },
  useEducationMembers: (enabled: boolean) => {
    state.membersEnabled.push(enabled);
    return { data: state.members };
  },
}));

import HomeworkCalendarWidget from '../HomeworkCalendarWidget';
import type { WidgetInstance } from '../../types';

const T = en.dashboard.widgets.homeworkCalendar;
const COMMON = en.dashboard.widgets.common;

type HwConfig = {
  window?: '1w' | '2w' | '1m';
  showCompleted?: boolean;
  view?: 'list' | 'month';
};

function makeInstance(config: HwConfig = {}): WidgetInstance<HwConfig> {
  return { id: 'hw-1', type: 'education.homeworkCalendar', config };
}

interface TaskFixture extends Record<string, unknown> {
  task_id: string;
  occurrence_date: string;
  due_at: string;
  title: string;
  is_completed: boolean;
  is_overdue: boolean;
  status: string;
}

function task(overrides: Partial<TaskFixture> = {}): TaskFixture {
  return {
    task_id: 'task-1',
    task_rule_id: 'rule-1',
    household_id: 'household-1',
    assigned_student_id: 'student-1',
    occurrence_date: '2026-09-11',
    due_at: '2026-09-11T10:30:00.000Z',
    title: '语文预习',
    description: '',
    subject_code: 'chinese',
    subject_color: '#D95D39',
    status: 'open',
    is_completed: false,
    is_overdue: false,
    ...overrides,
  };
}

/** Build a calendar payload from `[date, tasks]` pairs. */
function calendar(days: Array<[string, TaskFixture[]]>, stats?: Record<string, number>) {
  // The day the task sits under is authoritative — the API bins tasks by
  // occurrence_date, so the fixture does too rather than trusting whichever
  // default the `task()` builder happened to set.
  const built = days.map(([date, tasks]) => {
    const stamped = tasks.map((entry) => ({ ...entry, occurrence_date: date }));
    return {
      date,
      task_count: stamped.length,
      completed_count: stamped.filter((t) => t.is_completed).length,
      overdue_count: stamped.filter((t) => t.is_overdue).length,
      tasks: stamped,
    };
  });
  return {
    start_date: days[0]?.[0] ?? '2026-09-05',
    end_date: days[days.length - 1]?.[0] ?? '2026-09-11',
    days: built,
    stats: stats ?? { today_count: 0, week_count: 0, overdue_count: 0, completed_count: 0 },
  };
}

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="location">{location.pathname}</output>;
}

/**
 * Renders the widget the way the canvas does: the parent owns the config, and
 * an `updateConfig` patch comes back as a new `instance`. `useDashboardPrefs`
 * applies patches optimistically, so switching view or range re-renders the
 * widget immediately — the harness has to do the same or the switches look
 * inert.
 */
function renderWidget(
  config: HwConfig = {},
  onUpdateConfig?: (patch: Partial<HwConfig>) => void,
) {
  function Harness() {
    const [current, setCurrent] = useState<HwConfig>(config);
    const apply = (patch: Partial<HwConfig>) => {
      onUpdateConfig?.(patch);
      setCurrent((previous) => ({ ...previous, ...patch }));
    };
    return <HomeworkCalendarWidget instance={makeInstance(current)} updateConfig={apply} />;
  }

  return render(
    <MemoryRouter initialEntries={['/dashboard']} future={{ v7_startTransition: true }}>
      <Harness />
      <LocationProbe />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  state.isLoading = false;
  state.calendar = null;
  state.members = [];
  state.calls = [];
  state.membersEnabled = [];
  // Friday. Every bucket boundary in the cases below is measured from here.
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.setSystemTime(new Date('2026-09-11T09:00:00+09:00'));
});

afterEach(() => {
  vi.useRealTimers();
});

describe('HomeworkCalendarWidget', () => {
  it('shows the loading state while the calendar query is pending', () => {
    state.isLoading = true;
    renderWidget();
    expect(screen.getByText(COMMON.loading)).toBeInTheDocument();
  });

  it('shows the empty state instead of crashing when no day has tasks', () => {
    state.calendar = calendar([['2026-09-11', []]]);
    renderWidget();
    expect(screen.getByText(T.empty)).toBeInTheDocument();
    expect(screen.queryAllByTestId('homework-bucket')).toHaveLength(0);
  });

  it('buckets tasks into today / tomorrow / this week / next week / later', () => {
    state.calendar = calendar(
      [
        ['2026-09-11', [task({ task_id: 't-today' })]],
        ['2026-09-12', [task({ task_id: 't-tomorrow' })]],
        ['2026-09-15', [task({ task_id: 't-week' })]],
        ['2026-09-21', [task({ task_id: 't-next' })]],
        ['2026-09-28', [task({ task_id: 't-later' })]],
      ],
      { today_count: 1, week_count: 2, overdue_count: 0, completed_count: 0 },
    );
    renderWidget({ window: '1m' });

    const buckets = screen.getAllByTestId('homework-bucket');
    expect(buckets.map((b) => b.getAttribute('data-bucket'))).toEqual([
      'today',
      'tomorrow',
      'week',
      'next',
      'later',
    ]);
    expect(within(buckets[0]).getByText(T.bucket_today)).toBeInTheDocument();
    expect(within(buckets[4]).getByTestId('homework-task')).toHaveAttribute(
      'data-task-id',
      't-later',
    );
  });

  it('orders tasks nearest-due-first inside a bucket', () => {
    state.calendar = calendar([
      [
        '2026-09-15',
        [
          task({ task_id: 'late', due_at: '2026-09-15T20:00:00+09:00', title: '晚的' }),
          task({ task_id: 'early', due_at: '2026-09-15T08:00:00+09:00', title: '早的' }),
        ],
      ],
    ]);
    renderWidget();

    const rows = screen.getAllByTestId('homework-task');
    expect(rows.map((r) => r.getAttribute('data-task-id'))).toEqual(['early', 'late']);
  });

  it('marks an overdue task', () => {
    state.calendar = calendar([
      ['2026-09-11', [task({ task_id: 't-over', is_overdue: true })]],
    ]);
    renderWidget();
    expect(screen.getByTestId('homework-task')).toHaveAttribute('data-overdue', 'true');
  });

  it("draws the subject's own icon, tinted with the subject colour", () => {
    state.calendar = calendar([
      ['2026-09-11', [task({ subject_code: 'math', subject_color: '#277DA1' })]],
    ]);
    renderWidget();

    const icon = screen.getByTestId('homework-task').querySelector('svg[data-icon="数学"]') as
      | SVGElement
      | null;
    expect(icon).not.toBeNull();
    expect(icon!.style.color).toBe('rgb(39, 125, 161)');
  });

  it('falls back to a generic icon for a subject the batch does not cover', () => {
    state.calendar = calendar([
      ['2026-09-11', [task({ subject_code: 'calligraphy-extended' })]],
    ]);
    renderWidget();

    expect(
      screen.getByTestId('homework-task').querySelector('svg[data-icon]')?.getAttribute('data-icon'),
    ).toBe('书本');
  });

  it('hides completed tasks unless showCompleted is set', () => {
    state.calendar = calendar([
      [
        '2026-09-11',
        [
          task({ task_id: 't-open' }),
          task({ task_id: 't-done', status: 'completed', is_completed: true }),
        ],
      ],
    ]);

    const closed = renderWidget({ showCompleted: false });
    expect(screen.queryAllByTestId('homework-task')).toHaveLength(1);
    closed.unmount();

    renderWidget({ showCompleted: true });
    const rows = screen.getAllByTestId('homework-task');
    expect(rows).toHaveLength(2);
    expect(
      rows.find((r) => r.getAttribute('data-task-id') === 't-done'),
    ).toHaveAttribute('data-completed', 'true');
  });

  it('navigates to the education page when a row is clicked', () => {
    state.calendar = calendar([['2026-09-11', [task()]]]);
    renderWidget();
    fireEvent.click(screen.getByTestId('homework-task'));
    expect(screen.getByTestId('location')).toHaveTextContent('/education');
  });

  it("labels a task with the child's name from the member list", () => {
    state.calendar = calendar([
      ['2026-09-11', [task({ assigned_student_id: 'student-1' })]],
    ]);
    state.members = [{ user_id: 'student-1', name: 'henry', role: 'student' }];
    renderWidget();
    // The row renders "child · time" as one line, so match the name inside it.
    expect(within(screen.getByTestId('homework-task')).getByText(/henry/)).toBeInTheDocument();
  });

  it('renders the household stats strip', () => {
    state.calendar = calendar([['2026-09-11', [task()]]], {
      today_count: 2,
      week_count: 8,
      overdue_count: 3,
      completed_count: 21,
    });
    renderWidget();

    const strip = screen.getByTestId('homework-stats');
    expect(within(strip).getByText('2')).toBeInTheDocument();
    expect(within(strip).getByText('8')).toBeInTheDocument();
    expect(within(strip).getByText('3')).toBeInTheDocument();
    expect(within(strip).getByText('21')).toBeInTheDocument();
  });

  it('requests the current window first, with local dates', () => {
    state.calendar = calendar([['2026-09-11', [task()]]]);
    renderWidget({ window: '1w' });
    // The window looks forward from today, so the first thing a parent sees is
    // what is coming up; pressing back reveals the equal-length period before.
    expect(state.calls[0]).toMatchObject({ start_date: '2026-09-11', end_date: '2026-09-17' });
  });

  it('steps back a window at a time when the previous-week control is used', () => {
    state.calendar = calendar([['2026-09-11', [task()]]]);
    renderWidget({ window: '1w' });

    fireEvent.click(screen.getByTestId('homework-prev'));
    expect(state.calls.at(-1)).toMatchObject({
      start_date: '2026-09-04',
      end_date: '2026-09-10',
    });

    fireEvent.click(screen.getByTestId('homework-prev'));
    expect(state.calls.at(-1)).toMatchObject({
      start_date: '2026-08-28',
      end_date: '2026-09-03',
    });
  });

  it('returns to the current window from a look-back window', () => {
    state.calendar = calendar([['2026-09-11', [task()]]]);
    renderWidget({ window: '1w' });

    fireEvent.click(screen.getByTestId('homework-prev'));
    expect(screen.queryByTestId('homework-stats')).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId('homework-next'));
    expect(state.calls.at(-1)).toMatchObject({
      start_date: '2026-09-11',
      end_date: '2026-09-17',
    });
    expect(screen.getByTestId('homework-stats')).toBeInTheDocument();
  });

  it('does not persist the look-back offset across a remount', () => {
    state.calendar = calendar([['2026-09-11', [task()]]]);
    const first = renderWidget({ window: '1w' });
    fireEvent.click(screen.getByTestId('homework-prev'));
    first.unmount();

    renderWidget({ window: '1w' });
    expect(state.calls.at(-1)).toMatchObject({
      start_date: '2026-09-11',
      end_date: '2026-09-17',
    });
  });

  // ---------------------------------------------------------------------------
  // Period switcher — on the widget face, not buried in the settings dialog
  // ---------------------------------------------------------------------------
  it('re-queries with the chosen range when the period control is used', () => {
    state.calendar = calendar([['2026-09-11', [task()]]]);
    renderWidget({ window: '2w' });
    expect(state.calls.at(-1)).toMatchObject({
      start_date: '2026-09-11',
      end_date: '2026-09-24',
    });

    fireEvent.click(screen.getByTestId('homework-range-1w'));
    expect(state.calls.at(-1)).toMatchObject({
      start_date: '2026-09-11',
      end_date: '2026-09-17',
    });

    fireEvent.click(screen.getByTestId('homework-range-1m'));
    expect(state.calls.at(-1)).toMatchObject({
      start_date: '2026-09-11',
      end_date: '2026-10-11',
    });
  });

  it('persists the chosen range through updateConfig', () => {
    state.calendar = calendar([['2026-09-11', [task()]]]);
    const updateConfig = vi.fn();
    renderWidget({ window: '2w' }, updateConfig);

    fireEvent.click(screen.getByTestId('homework-range-1w'));
    expect(updateConfig).toHaveBeenCalledWith({ window: '1w' });
  });

  it('marks the active period control as selected', () => {
    state.calendar = calendar([['2026-09-11', [task()]]]);
    renderWidget({ window: '1w' });
    expect(screen.getByTestId('homework-range-1w')).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByTestId('homework-range-2w')).toHaveAttribute('aria-pressed', 'false');
  });

  // ---------------------------------------------------------------------------
  // Month view
  // ---------------------------------------------------------------------------

  /** Every date cell in the month grid, in grid order. */
  function dayCells(): HTMLElement[] {
    return screen.getAllByTestId('homework-day');
  }

  it('switches to the month grid and back', () => {
    state.calendar = calendar([['2026-09-11', [task()]]]);
    const updateConfig = vi.fn();
    renderWidget({ view: 'list' }, updateConfig);
    expect(screen.queryByTestId('homework-month-grid')).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId('homework-view-month'));
    expect(screen.getByTestId('homework-month-grid')).toBeInTheDocument();
    expect(updateConfig).toHaveBeenCalledWith({ view: 'month' });
  });

  it('renders every day of the displayed month', () => {
    state.calendar = calendar([['2026-09-11', [task()]]]);
    renderWidget({ view: 'month' });

    // September has 30 days.
    const cells = dayCells().filter((cell) => cell.getAttribute('data-in-month') === 'true');
    expect(cells).toHaveLength(30);
    expect(cells[0]).toHaveAttribute('data-date', '2026-09-01');
    expect(cells[29]).toHaveAttribute('data-date', '2026-09-30');
  });

  it('requests the whole displayed month', () => {
    state.calendar = calendar([['2026-09-11', [task()]]]);
    renderWidget({ view: 'month' });
    expect(state.calls.at(-1)).toMatchObject({
      start_date: '2026-09-01',
      end_date: '2026-09-30',
    });
  });

  it('starts on today and lists that day when a date is clicked', () => {
    state.calendar = calendar([
      ['2026-09-11', [task({ task_id: 't-today', title: '今天的作业' })]],
      ['2026-09-15', [task({ task_id: 't-later', title: '十五号的作业' })]],
    ]);
    renderWidget({ view: 'month' });

    // Default selection is today, so today's work is already listed below.
    let listed = screen.getAllByTestId('homework-day-task');
    expect(listed).toHaveLength(1);
    expect(listed[0]).toHaveAttribute('data-task-id', 't-today');

    const fifteenth = dayCells().find((cell) => cell.getAttribute('data-date') === '2026-09-15')!;
    fireEvent.click(fifteenth);

    listed = screen.getAllByTestId('homework-day-task');
    expect(listed).toHaveLength(1);
    expect(listed[0]).toHaveAttribute('data-task-id', 't-later');
    expect(fifteenth).toHaveAttribute('aria-pressed', 'true');
  });

  it('shows an empty state for a day with no homework', () => {
    state.calendar = calendar([['2026-09-11', [task()]]]);
    renderWidget({ view: 'month' });

    const empty = dayCells().find((cell) => cell.getAttribute('data-date') === '2026-09-20')!;
    fireEvent.click(empty);
    expect(screen.getByTestId('homework-day-empty')).toBeInTheDocument();
    expect(screen.queryAllByTestId('homework-day-task')).toHaveLength(0);
  });

  it('marks a day that holds overdue work', () => {
    state.calendar = calendar([
      ['2026-09-09', [task({ task_id: 't-over', is_overdue: true })]],
    ]);
    renderWidget({ view: 'month' });

    const ninth = dayCells().find((cell) => cell.getAttribute('data-date') === '2026-09-09')!;
    expect(ninth).toHaveAttribute('data-overdue', 'true');
    const clean = dayCells().find((cell) => cell.getAttribute('data-date') === '2026-09-10')!;
    expect(clean).toHaveAttribute('data-overdue', 'false');
  });

  it('shows one dot per subject on a day, capped with a remainder count', () => {
    state.calendar = calendar([
      [
        '2026-09-14',
        [
          task({ task_id: 'a', subject_code: 'chinese', subject_color: '#D95D39' }),
          task({ task_id: 'b', subject_code: 'math', subject_color: '#277DA1' }),
          task({ task_id: 'c', subject_code: 'english', subject_color: '#6A994E' }),
          task({ task_id: 'd', subject_code: 'biology', subject_color: '#2A9D8F' }),
        ],
      ],
    ]);
    renderWidget({ view: 'month' });

    const cell = dayCells().find((c) => c.getAttribute('data-date') === '2026-09-14')!;
    expect(cell.querySelectorAll('[data-dot]')).toHaveLength(3);
    expect(cell.textContent).toContain('+1');
  });

  it('navigates to the neighbouring month and selects its first day', () => {
    state.calendar = calendar([['2026-09-11', [task()]]]);
    renderWidget({ view: 'month' });

    fireEvent.click(screen.getByTestId('homework-prev'));
    expect(state.calls.at(-1)).toMatchObject({
      start_date: '2026-08-01',
      end_date: '2026-08-31',
    });
    expect(dayCells().find((c) => c.getAttribute('aria-pressed') === 'true')).toHaveAttribute(
      'data-date',
      '2026-08-01',
    );
  });

  it('hides the stats strip off the current month and offers a way back', () => {
    state.calendar = calendar([['2026-09-11', [task()]]], {
      today_count: 2,
      week_count: 8,
      overdue_count: 3,
      completed_count: 21,
    });
    renderWidget({ view: 'month' });

    expect(screen.getByTestId('homework-stats')).toBeInTheDocument();
    expect(screen.queryByTestId('homework-back-to-month')).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId('homework-prev'));
    expect(screen.queryByTestId('homework-stats')).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId('homework-back-to-month'));
    expect(screen.getByTestId('homework-stats')).toBeInTheDocument();
    expect(state.calls.at(-1)).toMatchObject({
      start_date: '2026-09-01',
      end_date: '2026-09-30',
    });
  });

  it('filters completed work out of the month grid too', () => {
    state.calendar = calendar([
      [
        '2026-09-11',
        [
          task({ task_id: 'open' }),
          task({ task_id: 'done', status: 'completed', is_completed: true }),
        ],
      ],
    ]);
    renderWidget({ view: 'month', showCompleted: false });
    expect(screen.getAllByTestId('homework-day-task')).toHaveLength(1);
  });

  it('groups tasks dated before today into their own bucket when looking back', () => {
    state.calendar = calendar([['2026-09-08', [task({ task_id: 't-past' })]]]);
    renderWidget({ window: '1w' });

    fireEvent.click(screen.getByTestId('homework-prev'));
    const buckets = screen.getAllByTestId('homework-bucket');
    expect(buckets[0]).toHaveAttribute('data-bucket', 'past');
    expect(within(buckets[0]).getByTestId('homework-task')).toHaveAttribute(
      'data-task-id',
      't-past',
    );
  });
});
