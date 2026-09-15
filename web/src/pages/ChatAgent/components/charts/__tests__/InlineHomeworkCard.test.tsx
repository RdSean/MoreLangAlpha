import { render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import artifactFixture from '@/contracts/__tests__/__fixtures__/homework-artifact.wire.json';
import InlineHomeworkCard from '../InlineHomeworkCard';

/**
 * The fixture is the same real artifact the contract tests use — captured from
 * the service, serialised with `model_dump(mode="json")`, identifiers and the
 * child's name replaced with stable stand-ins. Sharing it is deliberate: the
 * card is being tested against the payload the tool actually produces.
 */
const artifact = artifactFixture as unknown as Record<string, unknown>;

function clone(): Record<string, unknown> {
  return structuredClone(artifact);
}

function renderCard(payload: Record<string, unknown> = artifact, onClick?: () => void) {
  // Deliberately no QueryClientProvider and no router: this component must be a
  // leaf. If it ever grew a data hook, this render would throw.
  return render(<InlineHomeworkCard artifact={payload} onClick={onClick} />);
}

describe('InlineHomeworkCard', () => {
  it('renders the schedule the tool returned', () => {
    renderCard();
    expect(screen.getByTestId('inline-homework-card')).toBeInTheDocument();
    expect(screen.getByTestId('inline-homework-stats')).toBeInTheDocument();
    expect(screen.getAllByTestId('inline-homework-task').length).toBeGreaterThan(0);
  });

  it('shows one section per day that has work', () => {
    renderCard();
    const days = screen.getAllByTestId('inline-homework-day');
    expect(days.length).toBeGreaterThan(0);
    // Ascending, and only days that carry tasks.
    const dates = days.map((d) => d.getAttribute('data-date'));
    expect([...dates].sort()).toEqual(dates);
  });

  it("names the child from the payload's student_names", () => {
    renderCard();
    const task = screen.getAllByTestId('inline-homework-task')[0];
    // "Student 1" comes from the fixture's name map, so this passing means the
    // card read it from the payload rather than looking anything up.
    expect(within(task).getByText(/Student 1/)).toBeInTheDocument();
  });

  it('does not make a request to render', () => {
    // Belt and braces with the render setup: `useEducationMembers` and friends
    // require a QueryClientProvider, so a hook would have thrown by now.
    expect(() => renderCard()).not.toThrow();
  });

  it('marks overdue work', () => {
    const withOverdue = clone();
    const days = withOverdue.days as Array<{ tasks: Array<Record<string, unknown>> }>;
    days[0].tasks[0].is_overdue = true;
    renderCard(withOverdue);

    const marked = screen
      .getAllByTestId('inline-homework-task')
      .filter((task) => task.getAttribute('data-overdue') === 'true');
    expect(marked.length).toBeGreaterThan(0);
  });

  it('falls back to a default icon for a subject the icon set does not know', () => {
    const unknown = clone();
    const days = unknown.days as Array<{ tasks: Array<Record<string, unknown>> }>;
    days[0].tasks[0].subject_code = 'astrophysics';
    renderCard(unknown);

    const icons = screen
      .getAllByTestId('inline-homework-task')[0]
      .querySelectorAll('svg[data-icon]');
    expect(icons[0]?.getAttribute('data-icon')).toBe('书本');
  });

  // ---------------------------------------------------------------------------
  // The payoff of having a contract at all
  // ---------------------------------------------------------------------------

  it('renders a notice instead of throwing when the payload breaks the contract', () => {
    const broken = clone();
    delete broken.stats;
    renderCard(broken);

    expect(screen.getByTestId('inline-homework-invalid')).toBeInTheDocument();
    expect(screen.queryByTestId('inline-homework-card')).not.toBeInTheDocument();
  });

  it('renders a notice for a payload that is not a homework artifact at all', () => {
    renderCard({ type: 'something_else', days: [], start_date: 'x' });
    expect(screen.getByTestId('inline-homework-invalid')).toBeInTheDocument();
  });

  it('ignores an unknown extra key (older client, newer backend)', () => {
    const extended = clone();
    extended.added_later = { by: 'a future backend' };
    renderCard(extended);
    expect(screen.getByTestId('inline-homework-card')).toBeInTheDocument();
  });

  it('shows an empty state when the range holds no work', () => {
    const empty = clone();
    empty.days = (empty.days as Array<Record<string, unknown>>).map((day) => ({
      ...day,
      tasks: [],
      task_count: 0,
    }));
    renderCard(empty);
    expect(screen.getByTestId('inline-homework-empty')).toBeInTheDocument();
  });

  it('forwards a click so the transcript can open the detail panel', () => {
    const onClick = vi.fn();
    renderCard(artifact, onClick);
    screen.getByTestId('inline-homework-card').click();
    expect(onClick).toHaveBeenCalledTimes(1);
  });
});
