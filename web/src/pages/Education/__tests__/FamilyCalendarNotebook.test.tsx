import { fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import EducationNotebook from '../EducationNotebook';

const state = vi.hoisted(() => ({ error: false, extraEvents: 0 }));
vi.mock('../queries', () => ({ useEducationTaskCalendar: () => ({ data: { stats: { total_points: 0 }, days: [{ date: '2026-10-10', task_count: 1, tasks: [{ task_id: 'homework-1', title: '复习练习', subject_code: 'math' }] }] }, isLoading: false, isError: false }) }));
vi.mock('../calendarQueries', () => ({ useFamilyCalendarEvents: () => ({
  data: { timezone: 'Asia/Tokyo', events: [{ event_id: 'shared', source_id: 'school', source_name: '学校课表', title: '家庭阅读课', location: '图书馆', description: '带上阅读笔记', all_day: false, start_at: '2026-10-10T23:00:00+09:00', end_at: '2026-10-11T01:00:00+09:00', dates: ['2026-10-10', '2026-10-11'] }, ...Array.from({ length: state.extraEvents }, (_, index) => ({ event_id: `extra-${index}`, source_id: 'school', source_name: '学校课表', title: `补充课程${index + 1}`, location: '', description: '', all_day: false, start_at: '2026-10-10T23:00:00+09:00', end_at: '2026-10-11T01:00:00+09:00', dates: ['2026-10-10'] }))] },
  isLoading: false, isError: state.error, refetch: vi.fn(),
}) }));

beforeEach(() => { vi.useFakeTimers({ toFake: ['Date'] }); vi.setSystemTime(new Date('2026-10-10T06:00:00Z')); state.error = false; state.extraEvents = 0; });
afterEach(() => vi.useRealTimers());

function notebook(role: 'parent' | 'student' = 'parent', onCreateTask = vi.fn()) {
  return render(<EducationNotebook role={role} dictionaries={{ timezone: 'Asia/Tokyo', subjects: [], grade_levels: [], practice_sources: [] }} members={[{ user_id: 'student-1', role: 'student', name: '小明' }]} onCreateTask={onCreateTask} renderTasks={() => null} />);
}

it('opens creation for the double-clicked or selected date, only for parents', () => {
  const create = vi.fn();
  const view = notebook('parent', create);
  fireEvent.doubleClick(screen.getByRole('button', { name: /2026-10-23/ }));
  expect(create).toHaveBeenLastCalledWith('2026-10-23');
  fireEvent.click(screen.getByRole('button', { name: '创建作业' }));
  expect(create).toHaveBeenLastCalledWith('2026-10-23');
  view.unmount(); create.mockClear();
  notebook('student', create);
  fireEvent.doubleClick(screen.getByRole('button', { name: /2026-10-23/ }));
  expect(create).not.toHaveBeenCalled();
  expect(screen.queryByRole('button', { name: '创建作业' })).not.toBeInTheDocument();
});

it('swipes months without mistaking vertical movement, short drags or multitouch', () => {
  notebook();
  const grid = screen.getByLabelText('选择作业日期');
  const touch = (x: number, y: number) => ({ clientX: x, clientY: y });
  const drag = (x: number, y: number) => {
    fireEvent.touchStart(grid, { touches: [touch(200, 100)] });
    fireEvent.touchMove(grid, { touches: [touch(x, y)] });
    fireEvent.touchEnd(grid, { touches: [], changedTouches: [touch(x, y)] });
  };
  drag(80, 110);
  expect(screen.getByRole('button', { name: '2026-11-01' })).toHaveAttribute('aria-pressed', 'true');
  fireEvent.click(screen.getByRole('button', { name: '2026-11-05' }));
  expect(screen.getByRole('button', { name: '2026-11-01' })).toHaveAttribute('aria-pressed', 'true');
  drag(320, 110);
  expect(screen.getByRole('button', { name: /2026-10-01/ })).toHaveAttribute('aria-pressed', 'true');
  drag(180, 105); drag(100, 300);
  fireEvent.touchStart(grid, { touches: [touch(200, 100), touch(210, 110)] });
  fireEvent.touchEnd(grid, { touches: [], changedTouches: [touch(60, 100)] });
  expect(screen.getByRole('button', { name: /2026-10-01/ })).toHaveAttribute('aria-pressed', 'true');
  fireEvent.touchStart(grid, { touches: [touch(200, 100)] });
  fireEvent.touchCancel(grid);
  fireEvent.touchEnd(grid, { touches: [], changedTouches: [touch(60, 100)] });
  expect(screen.getByRole('button', { name: /2026-10-01/ })).toHaveAttribute('aria-pressed', 'true');
});

it('shows shared events across day boundaries and child filters', () => {
  notebook();
  expect(screen.getByRole('button', { name: /2026-10-10.*1项日程/ })).toBeVisible();
  expect(within(screen.getByRole('region', { name: '当天家庭日程' })).getByText('家庭阅读课')).toBeVisible();
  fireEvent.change(screen.getByLabelText('选择孩子'), { target: { value: 'student-1' } });
  expect(within(screen.getByRole('region', { name: '当天家庭日程' })).getByText('家庭阅读课')).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: /2026-10-11/ }));
  fireEvent.click(within(screen.getByRole('region', { name: '当天家庭日程' })).getByText('家庭阅读课'));
  expect(screen.getByText('图书馆')).toBeVisible();
  expect(screen.getByText('带上阅读笔记')).toBeVisible();
  expect(screen.getByLabelText('累计积分')).toHaveTextContent('0');
});

it('shows students the same household events', () => {
  notebook('student');
  expect(within(screen.getByRole('region', { name: '当天家庭日程' })).getByText('家庭阅读课')).toBeVisible();
  expect(screen.queryByLabelText('选择孩子')).not.toBeInTheDocument();
});

it('keeps homework available when shared events fail to load', () => {
  state.error = true;
  notebook();
  expect(screen.getByRole('alert')).toHaveTextContent('家庭日程加载失败');
  expect(screen.getByRole('heading', { name: '语文' })).toBeVisible();
});

it('previews two course titles in each date cell and reports overflow', () => {
  state.extraEvents = 3;
  notebook();
  const day = within(screen.getByRole('button', { name: /2026-10-10.*4项日程/ }));
  expect(day.getByText('家庭阅读课')).toBeVisible();
  expect(day.getByText('补充课程1')).toBeVisible();
  expect(day.queryByText('补充课程2')).not.toBeInTheDocument();
  expect(day.getByText('+2')).toBeVisible();
  expect(day.getByText('家庭阅读课').closest('[title]')).toHaveAttribute('title', '家庭阅读课');
  expect(day.getByText('家庭阅读课').compareDocumentPosition(day.getByTitle('作业：复习练习')) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(within(screen.getByRole('region', { name: '当天家庭日程' })).getByText('补充课程3')).toBeVisible();
});
