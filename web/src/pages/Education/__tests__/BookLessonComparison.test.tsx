import { useState } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import i18n from '@/i18n';
import { BookLessonReader } from '../components/BookLessonReader';

vi.mock('../components/EducationMarkdown', () => ({ default: ({ content }: { content: string }) => <div>{content}</div> }));
vi.mock('../components/BookLessonExport', () => ({ BookLessonExport: () => <button>Export PDF</button> }));
vi.mock('../components/LessonConversation', () => ({ default: function MockLessonConversation({ children }: {
  children: (state: { questionsBusy: boolean }) => React.ReactNode;
}) {
  const [draft, setDraft] = useState('');
  return <div>{children({ questionsBusy: false })}<textarea aria-label="Chat draft" value={draft} onChange={event => setDraft(event.target.value)} /></div>;
} }));

const material = {
  textbook_id: 'book', knowledge_point_id: 'kp', skill_kp_id: 'lesson', material_available: true,
  markdown: 'Current lesson', generated_at: null, depth: null, requirements: null, content_sha256: null,
};
function Reader() {
  const [enabled, setEnabled] = useState(false);
  return <BookLessonReader textbookId="book" assignmentId="assignment" title="Lesson" view="material" material={material}
    onViewChange={() => {}} comparisonEnabled={enabled} onComparisonChange={setEnabled}
    comparisonContent={<div data-testid="original">Original PDF</div>} />;
}

beforeEach(() => { void i18n.changeLanguage('zh-CN'); });
describe('lecture and original comparison', () => {
  it('toggles the original alongside the lecture without losing the Chat draft or DOM', () => {
    render(<Reader />);
    const input = screen.getByRole('textbox');
    fireEvent.change(input, { target: { value: 'My unfinished question' } });
    expect(screen.queryByTestId('original')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '对照原书' }));
    expect(screen.getByTestId('original')).toBeInTheDocument();
    expect(screen.getByText('Current lesson')).toBeInTheDocument();
    expect(screen.getByRole('textbox')).toBe(input);
    expect(input).toHaveValue('My unfinished question');
    expect(screen.getByRole('button', { name: '关闭原书对照' })).toHaveAttribute('aria-pressed', 'true');
    fireEvent.click(screen.getByRole('button', { name: '关闭原书对照' }));
    expect(screen.queryByTestId('original')).not.toBeInTheDocument();
    expect(screen.getByRole('textbox')).toBe(input);
    expect(input).toHaveValue('My unfinished question');
    expect(screen.getByRole('button', { name: 'Export PDF' })).toBeInTheDocument();
  });

  it('does not offer comparison for Markdown source or ungenerated lectures', () => {
    const { rerender } = render(<BookLessonReader textbookId="book" title="Lesson" view="source" onViewChange={() => {}}
      onComparisonChange={() => {}} comparisonContent={<div>PDF</div>} />);
    expect(screen.queryByRole('button', { name: '对照原书' })).not.toBeInTheDocument();
    rerender(<BookLessonReader textbookId="book" title="Lesson" view="material" material={{ ...material, material_available: false }}
      onViewChange={() => {}} onComparisonChange={() => {}} comparisonContent={<div>PDF</div>} />);
    expect(screen.queryByRole('button', { name: '对照原书' })).not.toBeInTheDocument();
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
  });
});
