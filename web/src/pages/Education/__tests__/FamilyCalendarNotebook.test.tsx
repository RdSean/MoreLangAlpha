import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import EducationNotebook from '../EducationNotebook';

const state = vi.hoisted(() => ({ error: false }));
vi.mock('../queries', () => ({ useEducationTaskCalendar: () => ({ data: { stats: { total_points: 0 }, days: [] }, isLoading: false, isError: false }) }));
vi.mock('../calendarQueries', () => ({ useFamilyCalendarEvents: () => ({
  data: { timezone: 'Asia/Tokyo', events: [{ event_id: 'shared', source_id: 'school', source_name: '学校课表', title: '家庭阅读课', location: '图书馆', description: '带上阅读笔记', all_day: false, start_at: '2026-10-10T23:00:00+09:00', end_at: '2026-10-11T01:00:00+09:00', dates: ['2026-10-10', '2026-10-11'] }] },
  isLoading: false, isError: state.error, refetch: vi.fn(),
}) }));

beforeEach(() => { vi.useFakeTimers({ toFake: ['Date'] }); vi.setSystemTime(new Date('2026-10-10T06:00:00Z')); state.error = false; });
afterEach(() => vi.useRealTimers());

function notebook(role: 'parent' | 'student' = 'parent') {
  return render(<EducationNotebook role={role} dictionaries={{ timezone: 'Asia/Tokyo', subjects: [], grade_levels: [], practice_sources: [] }} members={[{ user_id: 'student-1', role: 'student', name: '小明' }]} actions={null} renderTasks={() => null} />);
}

it('shows shared events across day boundaries and child filters', () => {
  notebook();
  expect(screen.getByRole('button', { name: /2026-10-10.*1项日程/ })).toBeVisible();
  expect(screen.getByText('家庭阅读课')).toBeVisible();
  fireEvent.change(screen.getByLabelText('选择孩子'), { target: { value: 'student-1' } });
  expect(screen.getByText('家庭阅读课')).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: /2026-10-11/ }));
  fireEvent.click(screen.getByText('家庭阅读课'));
  expect(screen.getByText('图书馆')).toBeVisible();
  expect(screen.getByText('带上阅读笔记')).toBeVisible();
  expect(screen.getByLabelText('累计积分')).toHaveTextContent('0');
});

it('shows students the same household events', () => {
  notebook('student');
  expect(screen.getByText('家庭阅读课')).toBeVisible();
  expect(screen.queryByLabelText('选择孩子')).not.toBeInTheDocument();
});

it('keeps homework available when shared events fail to load', () => {
  state.error = true;
  notebook();
  expect(screen.getByRole('alert')).toHaveTextContent('家庭日程加载失败');
  expect(screen.getByRole('heading', { name: '语文' })).toBeVisible();
});
