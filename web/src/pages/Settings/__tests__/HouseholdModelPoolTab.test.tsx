import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { HouseholdModelPoolTab } from '../panels/HouseholdModelPoolTab';

type Member = { user_id: string; name: string; role: 'parent' | 'student' } | null;

const state = vi.hoisted(() => ({
  member: { user_id: 'parent-1', name: '家长', role: 'parent' } as Member,
  pool: {
    endpoints: [{
      endpoint_id: 'endpoint-1',
      display_name: '家庭 DeepSeek Flash',
      provider: 'deepseek',
      model_id: 'deepseek-chat',
      base_url: 'https://api.deepseek.com',
      masked_api_key: 'sk-****1234',
      enabled: true,
      sort_order: 0,
    }],
    default_endpoint_id: 'endpoint-1' as string | null,
  },
  isLoading: false,
  isError: false,
  refetch: vi.fn(),
  create: vi.fn(),
  update: vi.fn(),
  remove: vi.fn(),
  setDefault: vi.fn(),
}));

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({ member: state.member }),
}));

vi.mock('../queries', () => ({
  useFamilyLlmPool: () => ({
    data: state.pool,
    isLoading: state.isLoading,
    isError: state.isError,
    refetch: state.refetch,
  }),
  useCreateFamilyLlmEndpoint: () => ({ mutateAsync: state.create, isPending: false }),
  useUpdateFamilyLlmEndpoint: () => ({ mutateAsync: state.update, isPending: false }),
  useDeleteFamilyLlmEndpoint: () => ({ mutateAsync: state.remove, isPending: false }),
  useSetFamilyLlmDefault: () => ({ mutateAsync: state.setDefault, isPending: false }),
}));

function renderTab() {
  return render(<HouseholdModelPoolTab />);
}

beforeEach(() => {
  state.member = { user_id: 'parent-1', name: '家长', role: 'parent' };
  state.pool = {
    endpoints: [{
      endpoint_id: 'endpoint-1',
      display_name: '家庭 DeepSeek Flash',
      provider: 'deepseek',
      model_id: 'deepseek-chat',
      base_url: 'https://api.deepseek.com',
      masked_api_key: 'sk-****1234',
      enabled: true,
      sort_order: 0,
    }],
    default_endpoint_id: 'endpoint-1',
  };
  state.isLoading = false;
  state.isError = false;
  state.refetch.mockReset();
  state.create.mockReset().mockResolvedValue({ endpoint_id: 'endpoint-2' });
  state.update.mockReset().mockResolvedValue({ endpoint_id: 'endpoint-1' });
  state.remove.mockReset().mockResolvedValue(undefined);
  state.setDefault.mockReset().mockResolvedValue({ default_endpoint_id: 'endpoint-1' });
});

describe('HouseholdModelPoolTab', () => {
  it('renders loading, recoverable error, and empty states', () => {
    state.isLoading = true;
    const { rerender } = renderTab();
    expect(screen.getByText('正在加载家庭模型池…')).toBeInTheDocument();

    state.isLoading = false;
    state.isError = true;
    rerender(<HouseholdModelPoolTab />);
    expect(screen.getByText('无法加载家庭模型池。')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '重试' }));
    expect(state.refetch).toHaveBeenCalledOnce();

    state.isError = false;
    state.pool = { endpoints: [], default_endpoint_id: null };
    rerender(<HouseholdModelPoolTab />);
    expect(screen.getByText('暂未添加家庭模型。')).toBeInTheDocument();
  });

  it('creates an endpoint and never renders an unmasked API key', async () => {
    renderTab();
    fireEvent.click(screen.getByRole('button', { name: '添加模型' }));
    fireEvent.change(screen.getByLabelText('显示名称'), { target: { value: '家庭 DeepSeek Flash' } });
    fireEvent.change(screen.getByLabelText('提供方'), { target: { value: 'deepseek' } });
    fireEvent.change(screen.getByLabelText('模型 ID'), { target: { value: 'deepseek-chat' } });
    fireEvent.change(screen.getByLabelText('Base URL（可选）'), { target: { value: 'https://api.deepseek.com' } });
    fireEvent.change(screen.getByLabelText('API Key（可选）'), { target: { value: 'secret-key' } });
    fireEvent.click(screen.getByRole('button', { name: '保存模型' }));

    await waitFor(() => expect(state.create).toHaveBeenCalledWith({
      display_name: '家庭 DeepSeek Flash',
      provider: 'deepseek',
      model_id: 'deepseek-chat',
      base_url: 'https://api.deepseek.com',
      api_key: 'secret-key',
      enabled: true,
      sort_order: 0,
    }));
    expect(screen.queryByText('secret-key')).not.toBeInTheDocument();
  });

  it('keeps an existing key on a blank edit and clears it only by explicit choice', async () => {
    renderTab();
    fireEvent.click(screen.getByRole('button', { name: '编辑 家庭 DeepSeek Flash' }));
    fireEvent.change(screen.getByLabelText('显示名称'), { target: { value: '新版 Flash' } });
    fireEvent.click(screen.getByRole('button', { name: '保存模型' }));

    await waitFor(() => expect(state.update).toHaveBeenCalledWith({
      endpointId: 'endpoint-1',
      input: expect.not.objectContaining({ api_key: expect.anything() }),
    }));

    fireEvent.click(screen.getByRole('button', { name: '编辑 家庭 DeepSeek Flash' }));
    fireEvent.click(screen.getByLabelText('清除当前 API Key'));
    fireEvent.click(screen.getByRole('button', { name: '保存模型' }));

    await waitFor(() => expect(state.update).toHaveBeenLastCalledWith({
      endpointId: 'endpoint-1',
      input: expect.objectContaining({ api_key: '' }),
    }));
  });

  it('updates enabled/default state and confirms deletion', async () => {
    renderTab();
    fireEvent.click(screen.getByLabelText('禁用 家庭 DeepSeek Flash'));
    await waitFor(() => expect(state.update).toHaveBeenCalledWith({
      endpointId: 'endpoint-1',
      input: { enabled: false },
    }));

    fireEvent.click(screen.getByRole('button', { name: '清除默认模型' }));
    await waitFor(() => expect(state.setDefault).toHaveBeenCalledWith(null));

    fireEvent.click(screen.getByRole('button', { name: '删除 家庭 DeepSeek Flash' }));
    fireEvent.click(screen.getByRole('button', { name: '删除模型' }));
    await waitFor(() => expect(state.remove).toHaveBeenCalledWith('endpoint-1'));
  });

  it('does not expose parent model management to a student', () => {
    state.member = { user_id: 'student-1', name: '小明', role: 'student' };
    renderTab();

    expect(screen.queryByRole('button', { name: '添加模型' })).not.toBeInTheDocument();
    expect(screen.queryByText('家庭模型池')).not.toBeInTheDocument();
  });
});
