import { fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import ChatInput from '../chat-input';

vi.mock('@/pages/ChatAgent/utils/api', () => ({
  getSkills: vi.fn().mockResolvedValue([]),
  getModelMetadata: vi.fn().mockResolvedValue({}),
}));

vi.mock('@/hooks/usePreferences', () => ({
  usePreferences: () => ({ preferences: null, isLoading: false }),
}));

vi.mock('@/hooks/useAllModels', () => ({
  useAllModels: () => ({ validModelNames: new Set<string>() }),
}));

vi.mock('@/lib/modelCapabilities', () => ({ supportsXhighEffort: () => false }));

const familyModels = [
  { modelKey: 'family:endpoint-1', displayName: '家庭 DeepSeek Flash' },
  { modelKey: 'family:endpoint-2', displayName: '家庭 Claude' },
];

function renderInput(props: Record<string, unknown> = {}) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <ChatInput onSend={vi.fn()} familyModels={familyModels} {...props} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('ChatInput family model selection', () => {
  beforeEach(() => {
    Element.prototype.scrollIntoView = vi.fn();
  });

  it('uses the server default without writing a student preference on first load', () => {
    const onFamilyModelSelect = vi.fn();
    renderInput({ initialModel: 'family:endpoint-1', onFamilyModelSelect });

    expect(screen.getByRole('button', { name: '家庭 DeepSeek Flash' })).toBeInTheDocument();
    expect(onFamilyModelSelect).not.toHaveBeenCalled();
  });

  it('shows only family models and saves a student selection with the opaque model key', () => {
    const onFamilyModelSelect = vi.fn();
    renderInput({ initialModel: 'family:endpoint-1', onFamilyModelSelect });

    fireEvent.click(screen.getByRole('button', { name: '家庭 DeepSeek Flash' }));
    fireEvent.click(screen.getByRole('menuitem', { name: '家庭 Claude' }));

    expect(onFamilyModelSelect).toHaveBeenCalledWith('family:endpoint-2');
    expect(screen.queryByText('管理模型')).not.toBeInTheDocument();
    expect(screen.queryByText('Sonnet 5')).not.toBeInTheDocument();
  });

  it('keeps a non-empty pool selectable when no default is configured', () => {
    renderInput({ initialModel: null });

    expect(screen.getByRole('button', { name: '选择模型' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '选择模型' }));
    expect(screen.getByRole('menuitem', { name: '家庭 DeepSeek Flash' })).toBeInTheDocument();
    expect(screen.queryByText('Sonnet 5')).not.toBeInTheDocument();
  });

  it('does not reveal a stale opaque key after the selected family endpoint is removed', () => {
    const onSend = vi.fn();
    renderInput({
      onSend,
      initialModel: 'family:removed-endpoint',
      familyModels: [{ modelKey: 'family:endpoint-2', displayName: '家庭 Claude' }],
    });

    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'hello' } });
    expect(screen.getByRole('button', { name: '选择模型' })).toBeInTheDocument();
    expect(screen.queryByText(/family:removed-endpoint/i)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Send message' })).toBeDisabled();
    expect(onSend).not.toHaveBeenCalled();
  });

  it('prevents a send with an empty family pool and offers a refresh action', () => {
    const onSend = vi.fn();
    const onRefreshFamilyModels = vi.fn();
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <ChatInput
            onSend={onSend}
            familyModels={[]}
            familyModelStatus="empty"
            onRefreshFamilyModels={onRefreshFamilyModels}
          />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'hello' } });
    expect(screen.getByText('暂无可用模型')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Send message' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: '刷新可用模型' }));
    expect(onRefreshFamilyModels).toHaveBeenCalledOnce();
    expect(onSend).not.toHaveBeenCalled();
  });
});
