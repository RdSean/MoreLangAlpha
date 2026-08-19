import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { FamilyAccountsTab } from '../panels/FamilyAccountsTab';

type MockMember = { user_id: string; name: string; role: 'parent' | 'student' } | null;

const state = vi.hoisted(() => ({
  member: { user_id: 'parent-1', name: '家长', role: 'parent' } as MockMember,
  children: [] as Array<Record<string, unknown>>,
  isLoading: false,
  create: vi.fn(),
}));

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({ member: state.member }),
}));

vi.mock('../queries', () => ({
  useFamilyChildren: () => ({ data: state.children, isLoading: state.isLoading, isError: false, refetch: vi.fn() }),
  useCreateChildAccount: () => ({ mutateAsync: state.create, isPending: false }),
}));

function renderTab() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}><FamilyAccountsTab onOpenChild={vi.fn()} /></QueryClientProvider>);
}

beforeEach(() => {
  state.member = { user_id: 'parent-1', name: '家长', role: 'parent' };
  state.children = [{
    user_id: 'student-1',
    email: null,
    username: 'xiaoming',
    name: '小明',
    role: 'student',
    household_id: 'household-1',
    flash_workspace: { workspace_id: 'flash-1', name: 'Flash', status: 'flash' },
  }];
  state.create.mockReset().mockResolvedValue({});
});

describe('FamilyAccountsTab', () => {
  it('shows a parent the child list and creates a child account', async () => {
    renderTab();

    expect(screen.getByRole('heading', { name: '家庭账户' })).toBeInTheDocument();
    expect(screen.getByText('小明')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '查看对话' })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '添加子女账户' }));
    fireEvent.change(screen.getByLabelText('用户名'), { target: { value: 'xiaoming' } });
    fireEvent.change(screen.getByLabelText('姓名'), { target: { value: '小明' } });
    fireEvent.change(screen.getByLabelText('初始密码'), { target: { value: 'a-long-enough-password' } });
    fireEvent.click(screen.getByRole('button', { name: '创建账户' }));

    await waitFor(() => expect(state.create).toHaveBeenCalledWith({
      username: 'xiaoming',
      name: '小明',
      password: 'a-long-enough-password',
    }));
  });

  it('does not present management controls to a student', () => {
    state.member = { user_id: 'student-1', name: '小明', role: 'student' };

    renderTab();

    expect(screen.getByText('只有家长可以管理家庭账户。')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '添加子女账户' })).not.toBeInTheDocument();
  });

  it('identifies an existing child without a local login username', () => {
    state.children[0].username = null;

    renderTab();

    expect(screen.getByText('未设置登录名')).toBeInTheDocument();
  });
});
