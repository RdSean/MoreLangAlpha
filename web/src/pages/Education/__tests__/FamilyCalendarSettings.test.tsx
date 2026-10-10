import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import FamilyCalendarSettings from '../FamilyCalendarSettings';

const state = vi.hoisted(() => ({ sources: [] as Array<Record<string, unknown>>, upload: vi.fn(), remove: vi.fn() }));
vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => ({ member: { role: 'parent', household_id: 'family-1' } }) }));
vi.mock('../calendarQueries', () => ({
  useFamilyCalendarSources: () => ({ data: state.sources, isLoading: false, isError: false }),
  useImportFamilyCalendar: () => ({ mutateAsync: state.upload, isPending: false }),
  useRemoveFamilyCalendar: () => ({ mutateAsync: state.remove, isPending: false }),
}));

beforeEach(() => {
  state.sources = [{ source_id: 'source-1', name: '学校课表', filename: 'classes.ics', event_count: 3, updated_at: '2026-10-10T00:00:00Z' }];
  state.upload.mockReset().mockResolvedValue({ name: '学校课表', event_count: 3 });
  state.remove.mockReset().mockResolvedValue(undefined);
});

it('imports a file into the household and reports the result', async () => {
  render(<FamilyCalendarSettings />);
  const file = new File(['calendar'], 'classes.ics', { type: 'text/calendar' });
  fireEvent.change(screen.getByLabelText('选择 ICS 文件'), { target: { files: [file] } });
  await waitFor(() => expect(state.upload).toHaveBeenCalledWith({ file, sourceId: undefined }));
  expect(await screen.findByRole('status')).toHaveTextContent('学校课表');
});

it('updates a specific source and confirms removal', async () => {
  render(<FamilyCalendarSettings />);
  fireEvent.click(screen.getByRole('button', { name: '更新学校课表' }));
  const file = new File(['new'], 'renamed.ics');
  fireEvent.change(screen.getByLabelText('选择 ICS 文件'), { target: { files: [file] } });
  await waitFor(() => expect(state.upload).toHaveBeenCalledWith({ file, sourceId: 'source-1' }));
  fireEvent.click(screen.getByRole('button', { name: '移除学校课表' }));
  expect(state.remove).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: '确认移除' }));
  await waitFor(() => expect(state.remove).toHaveBeenCalledWith('source-1'));
});

it('shows import errors without hiding existing sources', async () => {
  state.upload.mockRejectedValue({ response: { data: { detail: '文件无效' } } });
  render(<FamilyCalendarSettings />);
  fireEvent.change(screen.getByLabelText('选择 ICS 文件'), { target: { files: [new File(['bad'], 'bad.ics')] } });
  expect(await screen.findByRole('alert')).toHaveTextContent('文件无效');
  expect(screen.getByText('学校课表')).toBeVisible();
});
