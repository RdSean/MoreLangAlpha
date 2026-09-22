import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import BookProcessingPage from '../BookProcessingPage';

const state = vi.hoisted(() => ({
  create: vi.fn(),
  textbook: {
    textbook_id: 'textbook-1',
    household_id: 'household-1',
    title: '法语启蒙',
    slug: 'french-starter',
    versions: [
      {
        version_id: 'version-1',
        sequence: 1,
        status: 'review',
        chapter_count: 1,
        is_published: false,
        sources: [],
        chapters: [],
        assignments: [],
      },
    ],
  },
}));

vi.mock('../queries', () => ({
  useTextbook: () => ({ data: state.textbook, isLoading: false }),
  useBookPipelineMutations: () => ({
    create: {
      mutateAsync: state.create,
      isPending: false,
    },
  }),
}));

const placeholder =
  '例如：这是一本法语教材；忽略教师指导页；只提取学生活动页；数学教材中的公式和例题请按原顺序保留。';

function renderPage() {
  return render(
    <MemoryRouter
      initialEntries={['/textbooks/textbook-1/versions/version-1/processing']}
    >
      <Routes>
        <Route
          path="/textbooks/:textbookId/versions/:versionId/processing"
          element={<BookProcessingPage />}
        />
      </Routes>
    </MemoryRouter>,
  );
}

async function openDialog() {
  renderPage();
  const user = userEvent.setup();
  const launch = screen.getByRole('button', { name: '开始处理' });
  await user.click(launch);
  const dialog = await screen.findByRole('dialog');
  return { user, dialog, launch };
}

beforeEach(() => {
  state.create.mockReset().mockResolvedValue({
    generation_job_id: 'job-1',
    version_id: 'version-1',
    scope: 'book_pipeline',
    status: 'queued',
    attempt_count: 0,
    pause_after_chapter_analysis: false,
    reused_existing_job: false,
  });
  vi.spyOn(globalThis.crypto, 'randomUUID').mockReturnValue(
    'ba8a3e5c-c0b4-4a40-95ec-349310992445',
  );
});

describe('BookProcessingPage processing brief', () => {
  it('opens the optional brief dialog and submits an empty brief', async () => {
    const { user, dialog } = await openDialog();

    expect(within(dialog).getByText('补充要求（可选）')).toBeInTheDocument();
    expect(within(dialog).getByPlaceholderText(placeholder)).toBeInTheDocument();

    await user.click(within(dialog).getByRole('button', { name: '开始处理' }));

    await waitFor(() =>
      expect(state.create).toHaveBeenCalledWith({
        versionId: 'version-1',
        input: {
          processing_brief: '',
          request_id: 'ba8a3e5c-c0b4-4a40-95ec-349310992445',
          pause_after_chapter_analysis: false,
        },
      }),
    );
  });

  it('submits only once when confirm is double-clicked before resolving', async () => {
    let resolveCreate: ((value: unknown) => void) | undefined;
    state.create.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveCreate = resolve;
        }),
    );
    const { dialog, launch } = await openDialog();
    const confirm = within(dialog).getByRole('button', { name: '开始处理' });

    fireEvent.click(confirm);
    fireEvent.click(confirm);

    await waitFor(() => expect(state.create).toHaveBeenCalledTimes(1));
    expect(confirm).toBeDisabled();
    expect(launch).toBeDisabled();

    resolveCreate?.({
      generation_job_id: 'job-1',
      version_id: 'version-1',
      scope: 'book_pipeline',
      status: 'queued',
      attempt_count: 0,
      pause_after_chapter_analysis: false,
      reused_existing_job: false,
    });

    expect(await screen.findByText('处理任务已创建')).toBeInTheDocument();
    await userEvent
      .setup()
      .click(screen.getByRole('button', { name: '开始处理' }));
    const reopened = await screen.findByRole('dialog');
    expect(
      within(reopened).getByRole('button', { name: '开始处理' }),
    ).toBeEnabled();
  });
});
