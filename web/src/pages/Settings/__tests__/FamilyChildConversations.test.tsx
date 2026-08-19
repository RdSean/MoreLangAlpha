import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { FamilyChildConversations } from '../panels/FamilyChildConversations';

const state = vi.hoisted(() => ({
  workspace: { workspace_id: 'flash-1', name: 'Flash', status: 'flash' } as Record<string, unknown> | undefined,
  threads: [] as Array<Record<string, unknown>>,
  stream: vi.fn(),
}));

vi.mock('../queries', () => ({
  useFamilyChildWorkspace: () => ({ data: state.workspace, isLoading: false, isError: false, refetch: vi.fn() }),
  useFamilyChildThreads: () => ({ data: { threads: state.threads, total: state.threads.length, limit: 20, offset: 0 }, isLoading: false, isError: false, refetch: vi.fn() }),
}));

vi.mock('../api', () => ({
  streamFamilyChildThreadReplay: state.stream,
}));

function renderView() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}><FamilyChildConversations student={{ user_id: 'student-1', name: '小明' }} onBack={vi.fn()} /></QueryClientProvider>);
}

beforeEach(() => {
  state.workspace = { workspace_id: 'flash-1', name: 'Flash', status: 'flash' };
  state.threads = [{ thread_id: 'thread-1', workspace_id: 'flash-1', thread_index: 0, current_status: 'completed', title: '英语学习', first_query_content: '你好' }];
  state.stream.mockReset().mockImplementation(async (_studentId: string, _threadId: string, onEvent: (event: Record<string, unknown>) => void) => {
    onEvent({ event: 'user_message', content: '今天学习什么？' });
    onEvent({ event: 'message_chunk', role: 'assistant', content: '我们来复习单词。' });
    onEvent({ event: 'replay_done', thread_id: 'thread-1' });
  });
});

describe('FamilyChildConversations', () => {
  it('shows workspace state and renders a selected thread as read-only text', async () => {
    renderView();

    expect(screen.getByText('Flash 空间状态：可用')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '英语学习' }));

    expect(await screen.findByText('今天学习什么？')).toBeInTheDocument();
    expect(screen.getByText('我们来复习单词。')).toBeInTheDocument();
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /发送|编辑|删除|分享/ })).not.toBeInTheDocument();
  });

  it('shows an empty state when the child has no conversations', () => {
    state.threads = [];

    renderView();

    expect(screen.getByText('该 Flash 空间暂无对话记录。')).toBeInTheDocument();
  });

  it('shows a retry action when transcript loading fails', async () => {
    state.stream.mockRejectedValueOnce(new Error('offline'));

    renderView();
    fireEvent.click(screen.getByRole('button', { name: '英语学习' }));

    expect(await screen.findByText('无法加载这段对话。')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '重试' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '重试' }));
    await waitFor(() => expect(state.stream).toHaveBeenCalledTimes(2));
  });
});
