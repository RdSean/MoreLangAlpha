import { fireEvent, screen, waitFor } from '@testing-library/react';
import { renderWithProviders as render } from '@/test/utils';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { BookLessonReader } from '../components/BookLessonReader';
import { getWorkflowStatus, getReportBackStatus, fetchThreadTurns, getThreadFeedback } from '@/pages/ChatAgent/utils/api';
import { replayLessonConversation, getLessonConversationStatus } from '../api';

const state = vi.hoisted(() => ({ exportPdf: vi.fn(), ask: vi.fn(), history: [] }));
vi.mock('../api', () => ({ downloadBookLessonPdf: state.exportPdf, replayLessonConversation: vi.fn(), getLessonConversationStatus: vi.fn() }));
vi.mock('../queries', () => ({
  useLessonChatSpace: () => ({ data: { workspace_id: 'ws', conversation_thread_id: 'thread' }, isLoading: false, isFetching: false }),
  useBookQuestions: () => ({ data: state.history, isLoading: false, isFetching: false }),
  useLessonQuestion: () => ({ mutateAsync: state.ask }),
  useBookReadingMutation: () => ({ mutate: vi.fn() }),
}));
vi.mock('@/pages/ChatAgent/utils/api', async () => {
  const { apiMockModule } = await import('@/pages/ChatAgent/hooks/__tests__/chatHookHarness');
  return apiMockModule({ sendChatMessageStream: (...args: unknown[]) => state.ask({ onEvent: args[5] }) });
});
vi.mock('@/contexts/ThemeContext', () => ({ useTheme: () => ({ theme: 'light' }) }));
vi.mock('../components/EducationMarkdown', () => ({ default: ({ content }: { content: string }) => <p>{content}</p> }));
vi.mock('@/components/ui/chat-input.useVoiceInput', () => ({ speechSupported: false, useVoiceInput: () => ({ isListening: false, stopListening: vi.fn() }) }));

const material = { textbook_id: 'book', knowledge_point_id: 'kp', skill_kp_id: 'one', material_available: true, markdown: '# Lesson', generated_at: null, depth: null, requirements: null, content_sha256: null };
function Reader({ assignmentId, view = 'material', available = true }: { assignmentId?: string; view?: 'material' | 'source'; available?: boolean }) {
  return <BookLessonReader title="讲义" textbookId="book" assignmentId={assignmentId} material={{ ...material, material_available: available }} view={view} onViewChange={vi.fn()} />;
}

describe('lesson PDF export', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    state.exportPdf.mockResolvedValue(undefined);
    vi.mocked(getWorkflowStatus).mockResolvedValue({ can_reconnect: false, status: 'completed' });
    vi.mocked(getReportBackStatus).mockResolvedValue({ thread_id: 'thread', pending_report_back: false, report_back_run_id: null });
    vi.mocked(fetchThreadTurns).mockResolvedValue({ turns: [] });
    vi.mocked(getThreadFeedback).mockResolvedValue([]);
    vi.mocked(replayLessonConversation).mockResolvedValue(undefined);
    vi.mocked(getLessonConversationStatus).mockResolvedValue({ can_reconnect: false, status: 'completed', lesson_active: true });
    Object.defineProperty(HTMLElement.prototype, 'scrollTo', { configurable: true, value: vi.fn() });
  });
  it.each([undefined, 'assignment'])('exports material only by default for either reader (%s)', async (assignmentId) => {
    render(<Reader assignmentId={assignmentId} />);
    fireEvent.click(screen.getByRole('button', { name: '导出讲义 PDF' }));
    await waitFor(() => expect(state.exportPdf).toHaveBeenCalledWith(expect.objectContaining({ textbookId: 'book', knowledgePointId: 'kp', assignmentId, markdown: '# Lesson', includeQuestions: false })));
  });
  it('offers an explicit material and own questions option', async () => {
    render(<Reader assignmentId="assignment" />);
    await waitFor(() => expect(screen.getByRole('textbox')).toBeEnabled());
    await userEvent.click(screen.getByRole('button', { name: 'PDF 导出选项' }));
    await userEvent.click(screen.getByRole('menuitem', { name: '讲义及我的问答' }));
    await waitFor(() => expect(state.exportPdf).toHaveBeenCalledWith(expect.objectContaining({ includeQuestions: true, assignmentId: 'assignment' })));
  });
  it('does not offer export without a lecture or in source view', () => {
    const { rerender } = render(<Reader available={false} />);
    expect(screen.queryByRole('button', { name: '导出讲义 PDF' })).not.toBeInTheDocument();
    rerender(<Reader view="source" />);
    expect(screen.queryByRole('button', { name: '导出讲义 PDF' })).not.toBeInTheDocument();
  });
  it('reports export failure without losing the lecture and permits retry', async () => {
    state.exportPdf.mockRejectedValueOnce(new Error('PDF 导出超时，请重试。'));
    render(<Reader />);
    fireEvent.click(screen.getByRole('button', { name: '导出讲义 PDF' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('PDF 导出超时');
    expect(screen.getByText('# Lesson')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '导出讲义 PDF' }));
    await waitFor(() => expect(state.exportPdf).toHaveBeenCalledTimes(2));
  });
  it('disables question export during a live answer but leaves lecture export available', async () => {
    state.ask.mockImplementation(() => new Promise(() => {}));
    render(<Reader />);
    await waitFor(() => expect(screen.getByRole('textbox')).toBeEnabled());
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Why?' } });
    fireEvent.click(screen.getByRole('button', { name: '发送问题' }));
    await userEvent.click(screen.getByRole('button', { name: 'PDF 导出选项' }));
    expect(screen.getByRole('menuitem', { name: '讲义及我的问答' })).toHaveAttribute('data-disabled');
    expect(screen.getByRole('menuitem', { name: '仅讲义' })).not.toHaveAttribute('data-disabled');
  });
});
