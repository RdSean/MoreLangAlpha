import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import LessonConversation from '../components/LessonConversation';
import { BookLessonReader } from '../components/BookLessonReader';
import type { KnowledgePointMaterial } from '../types';

const state = vi.hoisted(() => ({ ask: vi.fn(), mark: vi.fn(), voice: vi.fn(), stop: vi.fn(), fetching: false }));
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

describe('lesson conversation pages', () => {
  beforeEach(() => { vi.clearAllMocks(); state.fetching = false; });
  it('shows an answer on a new page and returns to the lesson', async () => {
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
    expect(screen.queryByText('Original lesson')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '返回讲义' }));
    expect(screen.getByText('Original lesson')).toBeInTheDocument();
    await waitFor(() => expect(state.mark).toHaveBeenCalledWith({ knowledgePointId: 'kp', state: 'asked' }));
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
  it('clears the previous answer page when changing lessons', async () => {
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
