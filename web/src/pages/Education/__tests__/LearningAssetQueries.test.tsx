import { act, waitFor } from '@testing-library/react';
import { useQuery } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderHookWithProviders } from '@/test/utils';
import { queryKeys } from '@/lib/queryKeys';
import { useLearningAssetMutations, useStudentLearningItems } from '../queries';

const api = vi.hoisted(() => ({ list: vi.fn(), add: vi.fn(), update: vi.fn(), remove: vi.fn(), summarize: vi.fn(), chat: vi.fn() }));
vi.mock('../api', () => ({ listStudentLearningItems: api.list, createStudentLearningItem: api.add, updateStudentLearningItem: api.update, deleteStudentLearningItem: api.remove, generateStudentNodeSummary: api.summarize }));

describe('learning asset cache isolation', () => {
  beforeEach(() => { Object.values(api).forEach((fn) => fn.mockReset().mockResolvedValue([])); });
  it.each(['add', 'update', 'remove', 'summarize'] as const)('%s refreshes all current assignment notebook views without refetching Chat or another student', async (action) => {
    const { result } = renderHookWithProviders(() => {
      const point = useStudentLearningItems('assignment-a', { knowledgePointId: 'kp' });
      const unit = useStudentLearningItems('assignment-a', { skillNodeId: 'unit' });
      const other = useStudentLearningItems('assignment-b');
      const chat = useQuery({ queryKey: [...queryKeys.education.assignment('assignment-a'), 'chat-space'], queryFn: api.chat });
      return { point, unit, other, chat, mutations: useLearningAssetMutations() };
    });
    await waitFor(() => expect(result.current.point.isSuccess && result.current.unit.isSuccess && result.current.other.isSuccess && result.current.chat.isSuccess).toBe(true));
    await act(async () => {
      if (action === 'add') await result.current.mutations.add.mutateAsync({ assignmentId: 'assignment-a', knowledgePointId: 'kp', kind: 'note', content: 'note' });
      if (action === 'update') await result.current.mutations.update.mutateAsync({ assignmentId: 'assignment-a', itemId: 'item', content: 'note' });
      if (action === 'remove') await result.current.mutations.remove.mutateAsync({ assignmentId: 'assignment-a', itemId: 'item' });
      if (action === 'summarize') await result.current.mutations.summarize.mutateAsync({ assignmentId: 'assignment-a', skillNodeId: 'unit' });
    });
    expect(api.list.mock.calls.filter(([id]) => id === 'assignment-a')).toHaveLength(4);
    expect(api.list.mock.calls.filter(([id]) => id === 'assignment-b')).toHaveLength(1);
    expect(api.chat).toHaveBeenCalledTimes(1);
  });
});
