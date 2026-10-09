import { act, fireEvent, screen, waitFor } from '@testing-library/react';
import { renderWithProviders as render } from '@/test/utils';
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import LessonConversation from '../components/LessonConversation';
import { BookLessonReader } from '../components/BookLessonReader';
import type { KnowledgePointMaterial } from '../types';
import { getWorkflowStatus, getReportBackStatus, fetchThreadTurns, getThreadFeedback, getPreviewUrl } from '@/pages/ChatAgent/utils/api';
import { replayLessonConversation, getLessonConversationStatus } from '../api';

const state = vi.hoisted(() => ({ ask: vi.fn(), mark: vi.fn(), voice: vi.fn(), stop: vi.fn(), scroll: vi.fn(), fetching: false }));
vi.mock('../queries', () => ({
  useLessonChatSpace: () => ({ data: { workspace_id: 'ws', conversation_thread_id: 'thread' }, isLoading: false, isFetching: state.fetching }),
  useBookQuestions: () => ({ data: [], isLoading: false, isFetching: state.fetching }),
  useLessonQuestion: () => ({ mutateAsync: state.ask, isPending: false }),
  useBookReadingMutation: () => ({ mutate: state.mark, isError: false }),
}));
vi.mock('../api', () => ({ replayLessonConversation: vi.fn().mockResolvedValue(undefined), getLessonConversationStatus: vi.fn() }));
vi.mock('@/pages/ChatAgent/utils/api', async () => {
  const { apiMockModule } = await import('@/pages/ChatAgent/hooks/__tests__/chatHookHarness');
  return { ...apiMockModule({ sendChatMessageStream: (...args: unknown[]) => state.ask({ onEvent: args[5] }) }), getPreviewUrl: vi.fn() };
});
vi.mock('@/components/ui/chat-input.useVoiceInput', () => ({
  speechSupported: true,
  useVoiceInput: () => ({ isListening: false, toggleListening: state.voice, stopListening: state.stop }),
}));
vi.mock('../components/EducationMarkdown', () => ({ default: ({ content }: { content: string }) => <div>{content}</div> }));
vi.mock('@/contexts/ThemeContext', () => ({ useTheme: () => ({ theme: 'quiet' }) }));

describe('continuous lesson conversation', () => {
  beforeAll(() => Object.defineProperty(HTMLElement.prototype, 'scrollTo', { configurable: true, value: state.scroll }));
  afterAll(() => Reflect.deleteProperty(HTMLElement.prototype, 'scrollTo'));
  beforeEach(() => {
    vi.clearAllMocks(); state.fetching = false;
    vi.mocked(getWorkflowStatus).mockResolvedValue({ can_reconnect: false, status: 'completed' });
    vi.mocked(getReportBackStatus).mockResolvedValue({ thread_id: 'thread', pending_report_back: false, report_back_run_id: null });
    vi.mocked(fetchThreadTurns).mockResolvedValue({ turns: [] });
    vi.mocked(getThreadFeedback).mockResolvedValue([]);
    vi.mocked(replayLessonConversation).mockResolvedValue(undefined);
    vi.mocked(getLessonConversationStatus).mockResolvedValue({ can_reconnect: false, status: 'completed', lesson_active: true });
  });
  afterEach(() => vi.restoreAllMocks());
  it('keeps the lesson and all question rounds in one scroll flow', async () => {
    vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (this: HTMLElement) {
      return new DOMRect(0, this.classList.contains('lesson-turn') ? 1200 : 20, 800, 600);
    });
    state.ask.mockImplementation(async ({ onEvent }) => {
      onEvent({ event: 'message_chunk', role: 'assistant', content_type: 'reasoning_signal', content: 'start' });
      onEvent({ event: 'message_chunk', role: 'assistant', content_type: 'reasoning', content: 'Internal reasoning' });
      onEvent({ event: 'message_chunk', role: 'assistant', content_type: 'text', content: 'Answer from current lesson' });
    });
    render(<LessonConversation textbookId="book" knowledgePointId="kp"><div>Original lesson</div></LessonConversation>);
    await waitFor(() => expect(screen.getByRole('textbox')).toBeEnabled());
    fireEvent.change(screen.getByRole('textbox', { name: '讲义问题' }), { target: { value: 'Why?' } });
    fireEvent.click(screen.getByRole('button', { name: '发送问题' }));
    expect(await screen.findByText('Answer from current lesson')).toBeInTheDocument();
    expect(screen.getByText('Original lesson')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '返回讲义' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '下一页回答' })).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Why?' })).not.toBeInTheDocument();
    expect(screen.getByText('Why?').closest('section')).toHaveClass('lesson-turn');
    await waitFor(() => expect(state.mark).toHaveBeenCalledWith({ knowledgePointId: 'kp', state: 'asked' }));
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'And then?' } });
    fireEvent.click(screen.getByRole('button', { name: '发送问题' }));
    await waitFor(() => expect(screen.getAllByText('Answer from current lesson')).toHaveLength(2));
    expect(screen.getByText('Why?')).toBeInTheDocument();
    expect(screen.getByText('And then?')).toBeInTheDocument();
    expect(state.scroll).toHaveBeenLastCalledWith({ top: 1180, behavior: 'smooth' });
    expect(state.scroll).toHaveBeenCalledTimes(2);
  });
  it('hides the textbox in voice mode and exposes a long recording button', () => {
    render(<LessonConversation textbookId="book" knowledgePointId="kp"><div>Lesson</div></LessonConversation>);
    fireEvent.click(screen.getByRole('button', { name: '切换为语音输入' }));
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '按住说话' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '切换为文字输入' }));
    expect(screen.getByRole('textbox')).toBeInTheDocument();
  });
  it('waits for refreshed history before accepting a new question', () => {
    state.fetching = true;
    render(<LessonConversation textbookId="book" knowledgePointId="kp"><div>Lesson</div></LessonConversation>);
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'New question' } });
    expect(screen.getByRole('button', { name: '发送问题' })).toBeDisabled();
  });
  it('keeps a text-then-interrupt turn pending and renders the shared workspace card', async () => {
    state.ask.mockImplementation(async ({ onEvent }) => {
      onEvent({ event: 'message_chunk', role: 'assistant', content_type: 'text', content: 'Prepare a workspace' });
      onEvent({ event: 'interrupt', interrupt_id: 'confirm-1', action_requests: [{ type: 'create_workspace', workspace_name: 'Lesson project' }] });
    });
    render(<LessonConversation textbookId="book" knowledgePointId="kp"><div>Lesson</div></LessonConversation>);
    await waitFor(() => expect(screen.getByRole('button', { name: '发送问题' })).toBeDisabled());
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Make it' } });
    await waitFor(() => expect(screen.getByRole('button', { name: '发送问题' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: '发送问题' }));
    expect(await screen.findByText('Lesson project')).toBeInTheDocument();
    expect(screen.getByRole('textbox')).toBeDisabled();
    expect(state.mark).not.toHaveBeenCalledWith({ knowledgePointId: 'kp', state: 'asked' });
  });
  it('renders an HTML artifact through the shared isolated widget', async () => {
    state.ask.mockImplementation(async ({ onEvent }) => {
      onEvent({ event: 'artifact', artifact_type: 'html_widget', artifact_id: 'widget-1', payload: { html: '<h1>Lesson widget</h1>', title: 'Lesson widget' } });
    });
    const { container } = render(<LessonConversation textbookId="book" knowledgePointId="kp"><div>Lesson</div></LessonConversation>);
    await waitFor(() => expect(screen.getByRole('textbox')).toBeEnabled());
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Make a widget' } });
    fireEvent.click(screen.getByRole('button', { name: '发送问题' }));
    await waitFor(() => expect(container.querySelector('iframe')).toBeInTheDocument());
    expect(container.querySelector('iframe')?.getAttribute('sandbox')).not.toContain('allow-same-origin');
  });
  it('recovers file and preview references without starting a sandbox', async () => {
    vi.mocked(replayLessonConversation).mockImplementation(async (_book, _kp, _assignment, onEvent) => {
      onEvent({ event: 'user_message', turn_index: 4, content: 'Make files' });
      onEvent({ event: 'artifact', turn_index: 4, artifact_id: 'file-1', artifact_type: 'file_operation', payload: { file_path: 'work/lesson.md', operation: 'create' } });
      onEvent({ event: 'artifact', turn_index: 4, artifact_id: 'preview-1', artifact_type: 'preview_url', payload: { port: 3000, title: 'Lesson preview', command: 'pnpm dev' } });
    });
    render(<LessonConversation textbookId="book" knowledgePointId="kp"><div>Lesson</div></LessonConversation>);
    expect(await screen.findByRole('button', { name: 'work/lesson.md' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Lesson preview' })).toBeInTheDocument();
    expect(getPreviewUrl).not.toHaveBeenCalled();
    vi.mocked(getPreviewUrl).mockRejectedValue(new Error('Forbidden'));
    fireEvent.click(screen.getByRole('button', { name: 'Lesson preview' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('预览暂不可用或没有访问权限');
    expect(getPreviewUrl).toHaveBeenCalledWith('ws', 3000, 'pnpm dev');
  });
  it('attaches a live file to its answer when callbacks arrive before the next render', async () => {
    let calls = 0;
    state.ask.mockImplementation(async ({ onEvent }) => {
      calls++;
      onEvent({ event: 'message_chunk', role: 'assistant', content_type: 'text', content: `Answer ${calls}` });
      if (calls === 2) onEvent({ event: 'artifact', artifact_type: 'file_operation', artifact_id: 'second-file', payload: { file_path: 'work/second.md' } });
    });
    render(<LessonConversation textbookId="book" knowledgePointId="kp"><div>Lesson</div></LessonConversation>);
    await waitFor(() => expect(screen.getByRole('textbox')).toBeEnabled());
    for (const [index, question] of ['First question', 'Second question'].entries()) {
      fireEvent.change(screen.getByRole('textbox'), { target: { value: question } });
      fireEvent.click(screen.getByRole('button', { name: '发送问题' }));
      await screen.findByText(`Answer ${index + 1}`);
      await waitFor(() => expect(screen.getByRole('textbox')).toBeEnabled());
    }
    expect((await screen.findByRole('button', { name: 'work/second.md' })).closest('section')).toHaveAttribute('aria-label', '第 2 轮问答');
  });
  it('sends widget follow-up through the same scoped conversation', async () => {
    vi.mocked(replayLessonConversation).mockImplementation(async (_book, _kp, _assignment, onEvent) => {
      onEvent({ event: 'user_message', turn_index: 4, content: 'Make a widget' });
      onEvent({ event: 'artifact', turn_index: 4, artifact_id: 'widget', artifact_type: 'html_widget', payload: { html: '<p>Practice</p>', title: 'Practice' } });
    });
    state.ask.mockImplementation(async ({ onEvent }) => onEvent({ event: 'message_chunk', role: 'assistant', content_type: 'text', content: 'Widget answer' }));
    const { container } = render(<LessonConversation textbookId="book" knowledgePointId="kp"><div>Lesson</div></LessonConversation>);
    await waitFor(() => expect(screen.getByRole('textbox')).toBeEnabled());
    const iframe = container.querySelector('iframe')!;
    act(() => window.dispatchEvent(new MessageEvent('message', { source: iframe.contentWindow, data: { type: 'widget:sendPrompt', text: 'Explain this' } })));
    expect(await screen.findByText('Widget answer')).toBeInTheDocument();
    expect(screen.getByText('Explain this')).toBeInTheDocument();
    expect(state.ask).toHaveBeenCalledTimes(1);
  });
  it('offers a history recovery action after replay fails', async () => {
    vi.mocked(replayLessonConversation).mockRejectedValueOnce(new Error('Offline'));
    render(<LessonConversation textbookId="book" knowledgePointId="kp"><div>Lesson</div></LessonConversation>);
    fireEvent.click(await screen.findByRole('button', { name: '恢复会话' }));
    await waitFor(() => expect(replayLessonConversation).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument());
  });
  it('clears the previous conversation when changing lessons', async () => {
    state.ask.mockImplementation(async ({ onEvent }) => onEvent({ event: 'message_chunk', role: 'assistant', content_type: 'text', content: 'Previous answer' }));
    const material: KnowledgePointMaterial = {
      textbook_id: 'book', knowledge_point_id: 'kp-1', skill_kp_id: 'one', material_available: true,
      markdown: 'First lesson', generated_at: null, depth: null, requirements: null, content_sha256: null,
    };
    const props = { textbookId: 'book', title: 'Lesson', view: 'material' as const, onViewChange: vi.fn() };
    const { rerender } = render(<BookLessonReader {...props} material={material} />);
    await waitFor(() => expect(screen.getByRole('textbox')).toBeEnabled());
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Why?' } });
    fireEvent.click(screen.getByRole('button', { name: '发送问题' }));
    expect(await screen.findByText('Previous answer')).toBeInTheDocument();
    rerender(<BookLessonReader {...props} material={{ ...material, knowledge_point_id: 'kp-2', markdown: 'Second lesson' }} />);
    expect(screen.getByText('Second lesson')).toBeInTheDocument();
    expect(screen.queryByText('Previous answer')).not.toBeInTheDocument();
  });
});
