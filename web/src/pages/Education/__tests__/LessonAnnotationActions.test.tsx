import { fireEvent, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderWithProviders as render } from '@/test/utils';
import { LessonAnnotationsProvider, AnnotatedLesson, AnnotationSelectionActions } from '../components/LessonAnnotations';
import type { LearningItem } from '../types';

const state = vi.hoisted(() => ({ items: [] as LearningItem[], add: vi.fn(), update: vi.fn(), remove: vi.fn(), error: false, refetch: vi.fn() }));
vi.mock('../queries', () => ({
  useStudentLearningItems: () => ({ data: state.items, isError: state.error, refetch: state.refetch }),
  useLearningAssetMutations: () => ({ add: { mutateAsync: state.add }, update: { mutateAsync: state.update }, remove: { mutateAsync: state.remove } }),
}));
const anchor = { version: 1 as const, source: 'lesson' as const, start: 6, end: 11, exact: 'world', prefix: 'Hello ', suffix: '.', color: 'olive' as const };
function Reader() {
  return <LessonAnnotationsProvider assignmentId="assignment" knowledgePointId="kp" skillNodeId="unit">
    <AnnotatedLesson content="Hello world." />
    <AnnotationSelectionActions anchor={anchor} onDone={vi.fn()} />
  </LessonAnnotationsProvider>;
}
function item(kind: 'note' | 'highlight' = 'note'): LearningItem {
  return { item_id: 'item-1', assignment_id: 'assignment', knowledge_point_id: 'kp', kind, content: kind === 'note' ? 'Good phrase' : 'world', source_anchor: anchor, created_at: '', updated_at: '' };
}

describe('student lesson annotations', () => {
  beforeEach(() => { state.items = []; state.error = false; state.add.mockReset().mockResolvedValue(item()); state.update.mockReset().mockResolvedValue(item()); state.remove.mockReset().mockResolvedValue(undefined); });
  it('saves a highlight with the original quote, color and assignment/node scope', async () => {
    render(<Reader />);
    fireEvent.click(screen.getByRole('button', { name: '标记选段' }));
    fireEvent.click(screen.getByRole('button', { name: '赭黄色' }));
    fireEvent.click(screen.getByRole('button', { name: '保存标记' }));
    await waitFor(() => expect(state.add).toHaveBeenCalledWith({ assignmentId: 'assignment', knowledgePointId: 'kp', skillNodeId: 'unit', kind: 'highlight', content: 'world', sourceAnchor: { ...anchor, color: 'ochre' } }));
  });
  it('keeps annotation text on a failed save and supports retry', async () => {
    state.add.mockRejectedValueOnce(new Error('offline'));
    render(<Reader />);
    fireEvent.click(screen.getByRole('button', { name: '批注选段' }));
    fireEvent.change(screen.getByRole('textbox', { name: '批注内容' }), { target: { value: 'My understanding' } });
    fireEvent.click(screen.getByRole('button', { name: '保存批注' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('保存失败');
    expect(screen.getByRole('textbox', { name: '批注内容' })).toHaveValue('My understanding');
    fireEvent.click(screen.getByRole('button', { name: '保存批注' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(state.add).toHaveBeenLastCalledWith(expect.objectContaining({ kind: 'note', content: 'My understanding', sourceAnchor: anchor }));
  });
  it('restores and edits an existing note, retaining its quote anchor', async () => {
    state.items = [item()];
    render(<Reader />);
    fireEvent.click(screen.getByRole('button', { name: '查看批注' }));
    expect(screen.getByRole('textbox', { name: '批注内容' })).toHaveValue('Good phrase');
    fireEvent.change(screen.getByRole('textbox', { name: '批注内容' }), { target: { value: 'Better note' } });
    fireEvent.click(screen.getByRole('button', { name: '保存批注' }));
    await waitFor(() => expect(state.update).toHaveBeenCalledWith({ assignmentId: 'assignment', itemId: 'item-1', content: 'Better note', sourceAnchor: anchor }));
  });
  it('retains the note when delete fails and removes only the selected item on retry', async () => {
    state.items = [item()]; state.remove.mockRejectedValueOnce(new Error('offline'));
    render(<Reader />);
    fireEvent.click(screen.getByRole('button', { name: '查看批注' }));
    fireEvent.click(screen.getByRole('button', { name: '删除批注' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('删除失败');
    fireEvent.click(screen.getByRole('button', { name: '删除批注' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(state.remove).toHaveBeenLastCalledWith({ assignmentId: 'assignment', itemId: 'item-1' });
  });
  it('shows a retryable loading error instead of a false empty state', () => {
    state.error = true;
    render(<Reader />);
    expect(screen.getByRole('alert')).toHaveTextContent('标记与批注加载失败');
    fireEvent.click(screen.getByRole('button', { name: '重试加载笔记' }));
    expect(state.refetch).toHaveBeenCalled();
  });
  it('links hover and keyboard focus between the note and its source', () => {
    state.items = [item()];
    render(<Reader />);
    const mark = screen.getByRole('button', { name: '查看批注' });
    const note = screen.getByRole('article', { name: '批注 1' });
    fireEvent.pointerOver(mark);
    expect(note).toHaveAttribute('data-active', 'true');
    expect(mark).toHaveAttribute('data-active', 'true');
    fireEvent.pointerOut(mark);
    expect(note).not.toHaveAttribute('data-active');
    fireEvent.focus(screen.getByRole('button', { name: '定位批注 1 原文' }));
    expect(mark).toHaveAttribute('data-active', 'true');
  });
  it('locates the source from a margin quote without opening the editor', () => {
    state.items = [item()];
    render(<Reader />);
    const mark = screen.getByRole('button', { name: '查看批注' });
    const scroll = vi.fn();
    mark.scrollIntoView = scroll;
    fireEvent.click(screen.getByRole('button', { name: '定位批注 1 原文' }));
    expect(scroll).toHaveBeenCalledWith(expect.objectContaining({ block: 'center' }));
    expect(mark).toHaveFocus();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
  it('confirms margin deletion and retains the note on failure', async () => {
    state.items = [item()];
    state.remove.mockRejectedValueOnce(new Error('offline'));
    render(<Reader />);
    const note = screen.getByRole('article', { name: '批注 1' });
    fireEvent.click(screen.getByRole('button', { name: '删除批注 1' }));
    expect(state.remove).not.toHaveBeenCalled();
    expect(screen.getByRole('dialog', { name: '删除批注' })).toHaveTextContent('Good phrase');
    fireEvent.click(screen.getByRole('button', { name: '删除批注' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('删除失败');
    expect(note).toHaveTextContent('Good phrase');
    fireEvent.click(screen.getByRole('button', { name: '删除批注' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(state.remove).toHaveBeenLastCalledWith({ assignmentId: 'assignment', itemId: 'item-1' });
  });
});
