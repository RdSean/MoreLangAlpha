import { describe, expect, it } from 'vitest';
import { renderLessonSections } from '../lessonPdf';

describe('isolated lesson print markup', () => {
  it('renders real Chinese Markdown, tables and math without UI chrome', () => {
    const sections = renderLessonSections('## 位值\n\n$12 \\times 3 = 36$\n\n|数量|结果|\n|---|---|\n|12|36|', []);
    const doc = new DOMParser().parseFromString(sections[0].html, 'text/html');
    expect(doc.querySelectorAll('.katex')).toHaveLength(1);
    expect(doc.querySelector('.katex-error')).toBeNull();
    expect(doc.querySelector('table')).not.toBeNull();
    expect(doc.body.textContent).toContain('位值');
    expect(sections[0].role).toBe('material');
  });
  it('includes only explicit public user/assistant text, not other fields or process records', () => {
    const records = [
      { role: 'user', content: '问题', metadata: 'PRIVATE' },
      { role: 'tool', content: 'TOOL SECRET' },
      { role: 'assistant', content: '答案', reasoning: 'REASONING SECRET' },
      { role: 'assistant', content: 'PRIVATE THINKING', content_type: 'reasoning' },
    ];
    const sections = renderLessonSections('讲义正文', records);
    expect(sections.map((section) => section.role)).toEqual(['material', 'user', 'assistant']);
    expect(JSON.stringify(sections)).not.toMatch(/PRIVATE|SECRET|THINKING/);
  });
  it('reuses delimiter normalization while preserving code and rejecting scripts', () => {
    const [section] = renderLessonSections('\\(x^2\\)\n\n```text\n\\(not math\\)\n```\n\n<script>steal()</script>', []);
    const doc = new DOMParser().parseFromString(section.html, 'text/html');
    expect(doc.querySelectorAll('.katex')).toHaveLength(1);
    expect(doc.querySelector('code')?.textContent).toContain('\\(not math\\)');
    expect(doc.querySelector('script')).toBeNull();
  });
});
