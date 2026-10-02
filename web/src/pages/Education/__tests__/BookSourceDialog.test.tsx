import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

import i18n from '@/i18n';

import { BookSourceDialog } from '../components/BookSourceDialog';

const state = vi.hoisted(() => ({
  candidates: [] as Array<Record<string, unknown>>,
  createTextbook: vi.fn(),
}));

vi.mock('../queries', () => ({
  useManagedBookSourceCandidates: () => ({
    data: state.candidates,
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
  }),
  useManagedBookMutations: () => ({
    createTextbook: {
      mutateAsync: state.createTextbook,
      isPending: false,
    },
  }),
}));

const source = (overrides: Record<string, unknown> = {}) => ({
  document_id: 'doc-1',
  parse_job_id: 'job-old',
  primary_artifact_id: 'artifact-old',
  filename: 'lesson.pdf',
  media_type: 'application/pdf',
  parser_id: 'datalab',
  parser_name: 'Datalab',
  completed_at: '2026-10-01T09:00:00Z',
  content_sha256: 'a'.repeat(64),
  size_bytes: 1024,
  image_count: 2,
  ...overrides,
});

describe('BookSourceDialog', () => {
  beforeAll(async () => i18n.changeLanguage('zh-CN'));
  afterAll(async () => i18n.changeLanguage('en-US'));
  beforeEach(() => {
    vi.clearAllMocks();
    state.candidates = [
      source(),
      source({
        parse_job_id: 'job-new',
        primary_artifact_id: 'artifact-new',
        completed_at: '2026-10-02T09:00:00Z',
      }),
      source({
        document_id: 'doc-2',
        parse_job_id: 'job-other',
        primary_artifact_id: 'artifact-other',
        filename: 'other.pdf',
      }),
    ];
    state.createTextbook.mockResolvedValue({ textbook_id: 'book-1', job_id: 'book-job-1' });
  });

  it('limits a document entry to its parse results and defaults to the latest one', async () => {
    render(<BookSourceDialog open defaultDocumentId="doc-1" onOpenChange={vi.fn()} onCreated={vi.fn()} />);

    expect(screen.getAllByRole('radio')).toHaveLength(2);
    expect(screen.queryByText('other.pdf')).not.toBeInTheDocument();
    expect(screen.getAllByRole('radio')[0]).toBeChecked();
    expect(screen.getByRole('textbox', { name: '教材名称' })).toHaveValue('lesson');
  });

  it('creates one textbook from the selected frozen source and returns its job', async () => {
    const user = userEvent.setup();
    const onCreated = vi.fn();
    render(<BookSourceDialog open onOpenChange={vi.fn()} onCreated={onCreated} />);

    await user.clear(screen.getByRole('textbox', { name: '教材名称' }));
    await user.type(screen.getByRole('textbox', { name: '教材名称' }), '精读教材');
    await user.click(screen.getByRole('button', { name: '添加并分析' }));

    expect(state.createTextbook).toHaveBeenCalledWith({
      parse_job_id: 'job-new',
      primary_artifact_id: 'artifact-new',
      title: '精读教材',
      idempotency_key: expect.any(String),
    });
    expect(onCreated).toHaveBeenCalledWith({ textbook_id: 'book-1', job_id: 'book-job-1' });
  });
});
