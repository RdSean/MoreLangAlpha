import { act, renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, expect, it, vi } from 'vitest';
import { useFamilyCalendarEvents, useImportFamilyCalendar } from '../calendarQueries';

const state = vi.hoisted(() => ({ household: 'family-1', read: vi.fn(), upload: vi.fn() }));
vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => ({ member: { household_id: state.household } }) }));
vi.mock('../calendarApi', () => ({ getFamilyCalendarEvents: state.read, importFamilyCalendar: state.upload }));
const params = { start_date: '2026-10-01', end_date: '2026-10-31' };

beforeEach(() => { state.household = 'family-1'; state.read.mockReset().mockResolvedValue({ events: [] }); state.upload.mockReset().mockResolvedValue({ source_id: 'source-1' }); });

it('reuses month cache and invalidates it after importing', async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: React.ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  const first = renderHook(() => useFamilyCalendarEvents(params), { wrapper });
  await waitFor(() => expect(first.result.current.isSuccess).toBe(true));
  const second = renderHook(() => ({ calendar: useFamilyCalendarEvents(params), upload: useImportFamilyCalendar() }), { wrapper });
  expect(state.read).toHaveBeenCalledTimes(1);
  await act(() => second.result.current.upload.mutateAsync({ file: new File(['ICS'], 'school.ics') }));
  await waitFor(() => expect(state.read).toHaveBeenCalledTimes(2));
  first.unmount(); second.unmount(); client.clear();
});

it('does not reuse events from a different household', async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: React.ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  state.read.mockResolvedValueOnce({ events: [{ title: 'Family one' }] });
  const hook = renderHook(() => useFamilyCalendarEvents(params), { wrapper });
  await waitFor(() => expect(hook.result.current.isSuccess).toBe(true));
  state.household = 'family-2';
  hook.rerender();
  expect(hook.result.current.data).toBeUndefined();
  await waitFor(() => expect(state.read).toHaveBeenCalledTimes(2));
  await waitFor(() => expect(hook.result.current.data?.events).toEqual([]));
  hook.unmount(); client.clear();
});
