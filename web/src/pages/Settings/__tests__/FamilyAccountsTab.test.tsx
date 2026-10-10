import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { FamilyAccountsTab } from '../panels/FamilyAccountsTab';

type MockMember = { user_id: string; name: string; role: 'parent' | 'student' } | null;

const state = vi.hoisted(() => ({
  member: { user_id: 'parent-1', name: '家长', role: 'parent' } as MockMember,
  children: [] as Array<Record<string, unknown>>,
  isLoading: false,
  create: vi.fn(),
  updateProfile: vi.fn(),
  profile: { household_id: 'household-1', user_id: 'student-1', grade_code: 'g4' } as Record<string, unknown> | undefined,
  profileLoading: false,
  dictionaries: {
    subjects: [],
    grade_levels: [
      { code: 'g4', name: '四年级', stage: 'primary', sort_order: 4 },
      { code: 'g5', name: '五年级', stage: 'primary', sort_order: 5 },
    ],
    practice_sources: [],
  } as Record<string, unknown> | undefined,
  dictionariesLoading: false,
}));

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({ member: state.member }),
}));

vi.mock('../queries', () => ({
  useFamilyChildren: () => ({ data: state.children, isLoading: state.isLoading, isError: false, refetch: vi.fn() }),
  useCreateChildAccount: () => ({ mutateAsync: state.create, isPending: false }),
  useFamilyChildEducationProfile: () => ({ data: state.profile, isLoading: state.profileLoading }),
  useUpdateFamilyChildEducationProfile: () => ({ mutateAsync: state.updateProfile, isPending: false }),
  useEducationHomeworkDictionaries: () => ({ data: state.dictionaries, isLoading: state.dictionariesLoading }),
}));

function renderTab() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<MemoryRouter><QueryClientProvider client={queryClient}><FamilyAccountsTab onOpenChild={vi.fn()} /></QueryClientProvider></MemoryRouter>);
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
  state.updateProfile.mockReset().mockResolvedValue({ household_id: 'household-1', user_id: 'student-1', grade_code: 'g5' });
  state.profile = { household_id: 'household-1', user_id: 'student-1', grade_code: 'g4' };
  state.profileLoading = false;
  state.dictionaries = {
    subjects: [],
    grade_levels: [
      { code: 'g4', name: '四年级', stage: 'primary', sort_order: 4 },
      { code: 'g5', name: '五年级', stage: 'primary', sort_order: 5 },
    ],
    practice_sources: [],
  };
  state.dictionariesLoading = false;
});

describe('FamilyAccountsTab', () => {
  it('shows a parent the child list and creates a child account', async () => {
    renderTab();

    expect(screen.getByRole('heading', { name: '家庭账户' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '宝可梦卡牌' })).toHaveAttribute('href', '/settings/pokemon-cards');
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

  it('loads grade labels from the education dictionary and updates the selected child grade', async () => {
    renderTab();

    expect(screen.getByText('当前年级：四年级')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('小明的当前年级'), { target: { value: 'g5' } });

    await waitFor(() => expect(state.updateProfile).toHaveBeenCalledWith({ studentUserId: 'student-1', gradeCode: 'g5' }));
  });

  it('shows the unset-grade state and waits for the child profile to load', () => {
    state.profile = undefined;
    state.profileLoading = true;
    renderTab();

    expect(screen.getByText('正在加载年级…', { selector: 'p' })).toBeInTheDocument();

    state.profileLoading = false;
  });

  it('shows an explicit unset-grade label', () => {
    state.profile = { household_id: 'household-1', user_id: 'student-1', grade_code: null };
    renderTab();

    expect(screen.getByText('当前年级：未设置年级')).toBeInTheDocument();
  });

  it('waits for grade dictionary data before showing or editing an existing grade', () => {
    state.dictionaries = undefined;
    state.dictionariesLoading = true;
    renderTab();

    expect(screen.getByText('正在加载年级…', { selector: 'p' })).toBeInTheDocument();
    expect(screen.queryByText('当前年级：未设置年级')).not.toBeInTheDocument();
    expect(screen.getByLabelText('小明的当前年级')).toBeDisabled();
    expect(screen.getByLabelText('小明的当前年级')).toHaveValue('g4');
  });
});
