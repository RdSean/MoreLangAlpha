import { beforeEach, describe, expect, it, vi } from 'vitest';

const state = vi.hoisted(() => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
}));

vi.mock('@/api/client', () => ({
  api: {
    get: state.apiGet,
    post: state.apiPost,
  },
}));

vi.mock('@/pages/ChatAgent/utils/api/transport', () => ({
  streamFetch: vi.fn(),
}));

import {
  createChildAccount,
  getFamilyChildWorkspace,
  listFamilyChildThreads,
  listFamilyChildren,
} from '../api';
import { queryKeys } from '@/lib/queryKeys';

describe('family account API', () => {
  beforeEach(() => {
    state.apiGet.mockReset();
    state.apiPost.mockReset();
  });

  it('lists family children and creates a child account through auth endpoints', async () => {
    const child = { user_id: 'student-1', name: 'Student', username: 'student.lee', role: 'student', household_id: 'household-1', flash_workspace: { workspace_id: 'flash-1', name: 'Flash', status: 'flash' } };
    const createdChild = { user_id: 'student-1', email: null, name: 'Student', role: 'student', household_id: 'household-1' };
    state.apiGet.mockResolvedValueOnce({ data: [child] });
    state.apiPost.mockResolvedValueOnce({ data: createdChild });

    await expect(listFamilyChildren()).resolves.toEqual([child]);
    await expect(createChildAccount({ username: 'student.lee', password: 'a-long-enough-password', name: 'Student' })).resolves.toEqual(createdChild);

    expect(state.apiGet).toHaveBeenCalledWith('/api/v1/auth/children');
    expect(state.apiPost).toHaveBeenCalledWith('/api/v1/auth/children', {
      username: 'student.lee',
      password: 'a-long-enough-password',
      name: 'Student',
    });
  });

  it('loads a child workspace and paginated thread list', async () => {
    const workspace = { workspace_id: 'flash-1', name: 'Flash', status: 'flash' };
    const threads = { threads: [], total: 0, limit: 20, offset: 0 };
    state.apiGet.mockResolvedValueOnce({ data: workspace }).mockResolvedValueOnce({ data: threads });

    await expect(getFamilyChildWorkspace('student-1')).resolves.toEqual(workspace);
    await expect(listFamilyChildThreads('student-1', 20, 0)).resolves.toEqual(threads);

    expect(state.apiGet).toHaveBeenNthCalledWith(1, '/api/v1/auth/children/student-1/workspace');
    expect(state.apiGet).toHaveBeenNthCalledWith(2, '/api/v1/auth/children/student-1/threads', { params: { limit: 20, offset: 0, sort_by: 'updated_at', sort_order: 'desc' } });
  });

  it('uses hierarchical family query keys', () => {
    expect(queryKeys.settings.family.children()).toEqual(['settings', 'family', 'children']);
    expect(queryKeys.settings.family.threads('student-1', 20, 0)).toEqual(['settings', 'family', 'threads', 'student-1', 20, 0]);
  });
});
