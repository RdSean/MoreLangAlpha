import { act, fireEvent, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest';
import { renderWithProviders as render } from '@/test/utils';
import LessonConversation from '../components/LessonConversation';

const state = vi.hoisted(() => ({ send: vi.fn(), blocked: false, messages: [] as Array<Record<string, unknown>> }));
vi.mock('../queries', () => ({
  useLessonChatSpace: () => ({ data: { workspace_id: 'ws', conversation_thread_id: 'thread' } }),
  useBookReadingMutation: () => ({ mutate: vi.fn() }),
}));
vi.mock('../hooks/useLessonConversationSession', () => ({
  useLessonConversationSession: () => ({ messages: state.messages, handleSendMessage: state.send, lessonBlocked: state.blocked }),
}));
vi.mock('@/components/ui/chat-input.useVoiceInput', () => ({
  speechSupported: false,
  useVoiceInput: () => ({ isListening: false, stopListening: vi.fn() }),
}));
vi.mock('@/pages/ChatAgent/components/messageList/MessageContentSegments', () => ({
  MessageContentSegments: () => <div data-education-markdown="answer"><p>Answer selected passage.</p></div>,
}));

function Reader({ knowledgePointId = 'kp-1' }: { knowledgePointId?: string }) {
  return <LessonConversation textbookId="book" knowledgePointId={knowledgePointId}>
    <header>Not lesson prose</header>
    <div data-education-markdown="lesson"><p>First selected passage.</p><p>Second selected passage.</p></div>
  </LessonConversation>;
}

function select(node: Node) {
  const range = document.createRange();
  range.selectNodeContents(node);
  act(() => {
    const selection = window.getSelection()!;
    selection.removeAllRanges();
    selection.addRange(range);
    document.dispatchEvent(new Event('selectionchange'));
    document.dispatchEvent(new PointerEvent('pointerup', { bubbles: true }));
  });
}

async function addPassage(text = 'First selected passage.') {
  select(within(screen.getByRole('region', { name: '讲义与问答' })).getByText(text));
  fireEvent.click(await screen.findByRole('button', { name: /添加 \d+ 行到上下文|Add \d+ lines to context/ }));
}

describe('lesson selection context', () => {
  beforeEach(() => {
    state.send.mockReset().mockResolvedValue(undefined);
    state.blocked = false;
    state.messages = [];
    Object.defineProperty(Range.prototype, 'getBoundingClientRect', { configurable: true, value: () => new DOMRect(100, 100, 200, 20) });
    Object.defineProperty(Range.prototype, 'getClientRects', { configurable: true, value: () => [new DOMRect(100, 100, 200, 20)] });
    vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue(new DOMRect(0, 0, 800, 600));
  });
  afterEach(() => {
    window.getSelection()?.removeAllRanges();
    vi.restoreAllMocks();
    Reflect.deleteProperty(Range.prototype, 'getBoundingClientRect');
    Reflect.deleteProperty(Range.prototype, 'getClientRects');
  });

  it('stages a selection without editing the question and sends both once', async () => {
    render(<Reader />);
    const input = screen.getByRole('textbox', { name: '讲义问题' });
    fireEvent.change(input, { target: { value: 'Why is this true?' } });
    await addPassage();
    expect(input).toHaveValue('Why is this true?');
    const contextList = screen.getByRole('list', { name: '提问上下文' });
    expect(contextList).toHaveTextContent('讲义选段 · 1 行');
    expect(within(contextList).getByRole('listitem', { name: /讲义选段 · 1 行/ })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '发送问题' }));
    expect(state.send).toHaveBeenCalledWith(expect.stringContaining('Why is this true?'), false);
    expect(state.send.mock.calls[0][0]).toContain('<summary>[讲义选段');
    expect(state.send.mock.calls[0][0]).toContain('First selected passage.');
    expect(screen.queryByRole('list', { name: '提问上下文' })).not.toBeInTheDocument();
    fireEvent.change(input, { target: { value: 'Next question' } });
    await waitFor(() => expect(screen.getByRole('button', { name: '发送问题' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: '发送问题' }));
    expect(state.send).toHaveBeenLastCalledWith('Next question', false);
  });

  it('waits for the terminal pointer event before rendering the action', async () => {
    render(<Reader />);
    const node = screen.getByText('First selected passage.');
    const range = document.createRange();
    range.selectNodeContents(node);
    act(() => {
      const selection = window.getSelection()!;
      selection.removeAllRanges();
      selection.addRange(range);
      document.dispatchEvent(new Event('selectionchange'));
    });
    expect(screen.queryByRole('button', { name: /添加 \d+ 行到上下文|Add \d+ lines to context/ })).not.toBeInTheDocument();
    act(() => { document.dispatchEvent(new PointerEvent('pointerup', { bubbles: true })); });
    await screen.findByRole('button', { name: /添加 \d+ 行到上下文|Add \d+ lines to context/ });
  });

  it('labels a selection from an assistant answer separately from the lesson', async () => {
    state.messages = [{ id: 'answer-1', role: 'assistant', content: 'Answer selected passage.' }];
    render(<Reader />);
    select(screen.getByText('Answer selected passage.'));
    const add = await screen.findByRole('button', { name: /添加 \d+ 行到上下文|Add \d+ lines to context/ });
    fireEvent.click(add);
    expect(screen.getByRole('list', { name: '提问上下文' })).toHaveTextContent('回答选段 · 1 行');
  });

  it('previews the full selection when its compact indicator is hovered', async () => {
    render(<Reader />);
    await addPassage();
    const pill = within(screen.getByRole('list', { name: '提问上下文' })).getByRole('listitem');
    fireEvent.mouseEnter(pill);
    await waitFor(() => expect(screen.getByText('First selected passage.')).toBeVisible());
  });

  it('deduplicates repeated selection and removes only the requested passage', async () => {
    render(<Reader />);
    await addPassage();
    await addPassage();
    const list = screen.getByRole('list', { name: '提问上下文' });
    expect(within(list).getAllByRole('listitem')).toHaveLength(1);
    await addPassage('Second selected passage.');
    expect(within(list).getAllByRole('listitem')).toHaveLength(2);
    fireEvent.click(within(list).getAllByRole('button', { name: /移除选段/ })[0]);
    expect(within(list).getAllByRole('listitem')).toHaveLength(1);
  });

  it('ignores headers and cross-boundary selections and dismisses on scroll', async () => {
    render(<Reader />);
    select(screen.getByText('Not lesson prose'));
    expect(screen.queryByRole('button', { name: /添加 \d+ 行到上下文|Add \d+ lines to context/ })).not.toBeInTheDocument();
    select(screen.getByText('First selected passage.'));
    await screen.findByRole('button', { name: /添加 \d+ 行到上下文|Add \d+ lines to context/ });
    fireEvent.scroll(screen.getByRole('region', { name: '讲义与问答' }));
    expect(screen.queryByRole('button', { name: /添加 \d+ 行到上下文|Add \d+ lines to context/ })).not.toBeInTheDocument();
    const range = document.createRange();
    range.setStart(screen.getByText('Not lesson prose').firstChild!, 0);
    range.setEnd(screen.getByText('First selected passage.').firstChild!, 5);
    act(() => {
      window.getSelection()!.removeAllRanges();
      window.getSelection()!.addRange(range);
      document.dispatchEvent(new Event('selectionchange'));
      document.dispatchEvent(new PointerEvent('pointerup', { bubbles: true }));
    });
    expect(screen.queryByRole('button', { name: /添加 \d+ 行到上下文|Add \d+ lines to context/ })).not.toBeInTheDocument();
  });

  it('clears unsent context when switching knowledge points', async () => {
    const { rerender } = render(<Reader />);
    await addPassage();
    rerender(<Reader knowledgePointId="kp-2" />);
    expect(screen.queryByRole('list', { name: '提问上下文' })).not.toBeInTheDocument();
  });

  it('does not submit or offer new selection while the lesson is blocked', () => {
    state.blocked = true;
    render(<Reader />);
    select(screen.getByText('First selected passage.'));
    expect(screen.queryByRole('button', { name: /添加 \d+ 行到上下文|Add \d+ lines to context/ })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '发送问题' })).toBeDisabled();
    expect(state.send).not.toHaveBeenCalled();
  });
});
