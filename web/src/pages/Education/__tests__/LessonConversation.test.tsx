import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import LessonConversation from '../components/LessonConversation';
import { BookLessonReader } from '../components/BookLessonReader';
import type { KnowledgePointMaterial } from '../types';

const state = vi.hoisted(() => ({ ask: vi.fn(), mark: vi.fn(), voice: vi.fn(), stop: vi.fn(), scroll: vi.fn(), fetching: false }));
vi.mock('../queries', () => ({
  useBookQuestions: () => ({ data: [], isLoading: false, isFetching: state.fetching }),
  useLessonQuestion: () => ({ mutateAsync: state.ask, isPending: false }),
  useBookReadingMutation: () => ({ mutate: state.mark, isError: false }),
}));
vi.mock('@/components/ui/chat-input.useVoiceInput', () => ({
  speechSupported: true,
  useVoiceInput: () => ({ isListening: false, toggleListening: state.voice, stopListening: state.stop }),
}));
vi.mock('../components/EducationMarkdown', () => ({ default: ({ content }: { content: string }) => <div>{content}</div> }));

describe('continuous lesson conversation', () => {
  beforeAll(() => Object.defineProperty(HTMLElement.prototype, 'scrollTo', { configurable: true, value: state.scroll }));
  afterAll(() => Reflect.deleteProperty(HTMLElement.prototype, 'scrollTo'));
  beforeEach(() => { vi.clearAllMocks(); state.fetching = false; });
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
    fireEvent.change(screen.getByRole('textbox', { name: '讲义问题' }), { target: { value: 'Why?' } });
    fireEvent.click(screen.getByRole('button', { name: '发送问题' }));
    expect(await screen.findByText('Answer from current lesson')).toBeInTheDocument();
    expect(screen.queryByText(/Internal reasoning/)).not.toBeInTheDocument();
    expect(screen.getByText('Original lesson')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '返回讲义' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '下一页回答' })).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Why?' }).closest('section')).toHaveClass('lesson-turn');
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
  it('clears the previous conversation when changing lessons', async () => {
    state.ask.mockImplementation(async ({ onEvent }) => onEvent({ event: 'message_chunk', role: 'assistant', content_type: 'text', content: 'Previous answer' }));
    const material: KnowledgePointMaterial = {
      textbook_id: 'book', knowledge_point_id: 'kp-1', skill_kp_id: 'one', material_available: true,
      markdown: 'First lesson', generated_at: null, depth: null, requirements: null, content_sha256: null,
    };
    const props = { textbookId: 'book', title: 'Lesson', view: 'material' as const, onViewChange: vi.fn() };
    const { rerender } = render(<BookLessonReader {...props} material={material} />);
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Why?' } });
    fireEvent.click(screen.getByRole('button', { name: '发送问题' }));
    expect(await screen.findByText('Previous answer')).toBeInTheDocument();
    rerender(<BookLessonReader {...props} material={{ ...material, knowledge_point_id: 'kp-2', markdown: 'Second lesson' }} />);
    expect(screen.getByText('Second lesson')).toBeInTheDocument();
    expect(screen.queryByText('Previous answer')).not.toBeInTheDocument();
  });
});
