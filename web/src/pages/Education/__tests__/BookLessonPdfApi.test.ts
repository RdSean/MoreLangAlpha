import { Blob as NodeBlob } from 'node:buffer';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/api/client', () => ({ api: { defaults: { baseURL: '' }, get: vi.fn(), post: vi.fn() } }));

import { api } from '@/api/client';
import { downloadBookLessonPdf } from '../api';

describe('lesson PDF download adapter', () => {
  const createObjectURL = vi.fn(() => 'blob:lesson');
  const revokeObjectURL = vi.fn();
  const options = () => ({ textbookId: 'book', knowledgePointId: 'kp', markdown: '讲义正文', includeQuestions: false, signal: new AbortController().signal });

  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
    vi.stubGlobal('Blob', NodeBlob);
    vi.stubGlobal('URL', class extends URL {
      static createObjectURL = createObjectURL;
      static revokeObjectURL = revokeObjectURL;
    });
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    vi.mocked(api.post).mockResolvedValue({ data: new Blob(['%PDF-test'], { type: 'application/pdf' }), headers: { 'content-disposition': "attachment; filename*=UTF-8''%E8%AE%B2%E4%B9%89.pdf" } });
  });

  afterEach(() => {
    vi.runOnlyPendingTimers();
    vi.useRealTimers();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('downloads only the lesson by default and releases its temporary URL', async () => {
    await downloadBookLessonPdf(options());
    expect(api.get).not.toHaveBeenCalled();
    const [, payload, config] = vi.mocked(api.post).mock.calls[0];
    expect(payload).toMatchObject({ include_questions: false, font_css: '', sections: [{ role: 'material', markdown: '讲义正文' }] });
    expect(config).toMatchObject({ responseType: 'blob', timeout: 65_000 });
    const link = vi.mocked(HTMLAnchorElement.prototype.click).mock.contexts[0] as HTMLAnchorElement;
    expect(link.download).toBe('讲义.pdf');
    expect(link.isConnected).toBe(false);
    expect(revokeObjectURL).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1000);
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:lesson');
  });

  it('uses the same user/knowledge-point history and excludes process content', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: [
      { role: 'user', content: '问题' },
      { role: 'assistant', content: '回答', reasoning: 'PRIVATE' },
      { role: 'tool', content: 'PRIVATE TOOL' },
      { role: 'assistant', content: 'PRIVATE THOUGHT', content_type: 'reasoning' },
    ] });
    const input = { ...options(), includeQuestions: true, assignmentId: 'assignment' };
    await downloadBookLessonPdf(input);
    expect(api.get).toHaveBeenCalledWith('/api/v1/education/textbooks/book/knowledge-points/kp/questions', { params: { assignment_id: 'assignment' }, signal: input.signal });
    const payload = vi.mocked(api.post).mock.calls[0][1] as { sections: { role: string }[] };
    expect(payload.sections.map((section) => section.role)).toEqual(['material', 'user', 'assistant']);
    expect(JSON.stringify(payload)).not.toContain('PRIVATE');
  });

  it('shows the server error from a failed Blob response without downloading', async () => {
    vi.mocked(api.post).mockRejectedValue({ response: { data: new Blob([JSON.stringify({ detail: '讲义已更新，请刷新' })], { type: 'application/json' }) } });
    await expect(downloadBookLessonPdf(options())).rejects.toThrow('讲义已更新，请刷新');
    expect(createObjectURL).not.toHaveBeenCalled();
  });

  it('rejects non-PDF responses instead of downloading an error page', async () => {
    vi.mocked(api.post).mockResolvedValue({ data: new Blob(['error'], { type: 'text/html' }), headers: {} });
    await expect(downloadBookLessonPdf(options())).rejects.toThrow('PDF 导出响应无效');
    expect(createObjectURL).not.toHaveBeenCalled();
  });

  it('does not start a download after a cancelled request completes', async () => {
    const controller = new AbortController();
    vi.mocked(api.post).mockImplementation(async () => {
      controller.abort();
      return { data: new Blob(['%PDF-test'], { type: 'application/pdf' }), headers: {} };
    });
    await downloadBookLessonPdf({ ...options(), signal: controller.signal });
    expect(createObjectURL).not.toHaveBeenCalled();
  });
});
