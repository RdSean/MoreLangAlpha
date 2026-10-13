import { fireEvent, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { renderWithProviders as render } from '@/test/utils';
import EducationMarkdown from '../components/EducationMarkdown';
import { annotationPlugin, captureLessonAnchor, parseLessonAnchor, resolveAnchor } from '../components/lessonAnnotationAnchors';

describe('lesson annotation anchors', () => {
  it('captures across inline formatting and restores the exact range', () => {
    render(<EducationMarkdown content={'Hello **world** and [friends](https://example.com).\n\nHello world again.'} annotationOptions={{ items: [] }} />);
    const spans = Array.from(document.querySelectorAll<HTMLElement>('[data-lesson-text-start]'));
    expect(spans.length).toBeGreaterThan(2);
    const range = document.createRange();
    range.setStart(spans[0].firstChild!, 6);
    range.setEnd(spans[2].firstChild!, 4);
    const anchor = captureLessonAnchor(document.querySelector('[data-education-markdown]')!, range);
    expect(anchor?.exact).toBe('world and');
    expect(resolveAnchor('Hello world and friends.Hello world again.', anchor!)).toEqual({ start: 6, end: 15 });
  });
  it('relocates with context after editing and rejects ambiguous or missing quotes', () => {
    const anchor = { version: 1 as const, source: 'lesson' as const, start: 6, end: 11, exact: 'world', prefix: 'Hello ', suffix: ' again.', color: 'olive' as const };
    expect(resolveAnchor('New intro. Hello world again.', anchor)).toEqual({ start: 17, end: 22 });
    expect(resolveAnchor('world and world', { ...anchor, prefix: '', suffix: '' })).toBeNull();
    expect(resolveAnchor('Changed lecture.', anchor)).toBeNull();
  });
  it('renders overlapping marks without losing text or wrapping code', () => {
    const tree = { type: 'root', children: [{ type: 'element', tagName: 'p', children: [{ type: 'text', value: 'abcdef' }] }, { type: 'element', tagName: 'pre', children: [{ type: 'text', value: 'secret' }] }] };
    annotationPlugin({ items: [
      { item_id: 'one', kind: 'highlight', source_anchor: { version: 1, source: 'lesson', start: 1, end: 4, exact: 'bcd', prefix: 'a', suffix: 'ef', color: 'olive' } },
      { item_id: 'two', kind: 'note', source_anchor: { version: 1, source: 'lesson', start: 3, end: 6, exact: 'def', prefix: 'abc', suffix: '', color: 'ochre' } },
    ] })(tree);
    expect(JSON.stringify(tree)).toContain('two one');
    expect(JSON.stringify(tree.children[1])).not.toContain('data-lesson-text-start');
  });
  it('supports keyboard access to restored marks', () => {
    const open = vi.fn();
    render(<EducationMarkdown content="Hello world." annotationOptions={{ items: [{ item_id: 'note-1', kind: 'note', source_anchor: { version: 1, source: 'lesson', start: 6, end: 11, exact: 'world', prefix: 'Hello ', suffix: '.', color: 'olive' } }], onOpen: open }} />);
    const mark = screen.getByRole('button', { name: '查看批注' });
    fireEvent.keyDown(mark, { key: 'Enter' });
    expect(open).toHaveBeenCalledWith('note-1');
    expect(mark).toHaveTextContent('world');
  });
  it('opens a note before its overlapping highlight regardless of response order', () => {
    const open = vi.fn();
    const anchor = { version: 1, source: 'lesson', start: 6, end: 11, exact: 'world', prefix: 'Hello ', suffix: '.', color: 'olive' };
    render(<EducationMarkdown content="Hello world." annotationOptions={{ items: [{ item_id: 'mark', kind: 'highlight', source_anchor: anchor }, { item_id: 'note', kind: 'note', source_anchor: anchor }], onOpen: open }} />);
    fireEvent.click(screen.getByRole('button', { name: '查看批注' }));
    expect(open).toHaveBeenCalledWith('note');
  });
  it('rejects invalid stored anchors and selections crossing excluded math or code', () => {
    expect(parseLessonAnchor({ version: 1, source: 'lesson', start: -1 })).toBeNull();
    render(<EducationMarkdown content={'Hello **world** and `code`.\n\n$x^2$'} annotationOptions={{ items: [] }} />);
    const root = document.querySelector('[data-education-markdown]')!;
    const range = document.createRange(); range.selectNodeContents(root);
    expect(captureLessonAnchor(root, range)).toBeNull();
    expect(root.querySelector('code [data-lesson-text-start], .katex [data-lesson-text-start]')).toBeNull();
  });
});
