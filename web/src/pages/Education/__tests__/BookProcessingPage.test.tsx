import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {
  MemoryRouter,
  Route,
  Routes,
  useLocation,
} from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import BookProcessingPage from '../BookProcessingPage';

const state = vi.hoisted(() => ({
  create: vi.fn(),
  cancel: vi.fn(),
  cancelPending: false,
  progress: null as Record<string, unknown> | null,
  progressCalls: [] as Array<[string | undefined, boolean]>,
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
  useBookPipelineProgress: (
    jobId: string | undefined,
    enabled: boolean,
  ) => {
    state.progressCalls.push([jobId, enabled]);
    return {
      data: enabled ? state.progress : undefined,
      isPending: false,
      isError: false,
    };
  },
  useBookPipelineMutations: () => ({
    create: {
      mutateAsync: state.create,
      isPending: false,
    },
    cancel: {
      mutateAsync: state.cancel,
      isPending: state.cancelPending,
    },
  }),
}));

const placeholder =
  '例如：这是一本法语教材；忽略教师指导页；只提取学生活动页；数学教材中的公式和例题请按原顺序保留。';

function renderPage(
  initialEntry = '/textbooks/textbook-1/versions/version-1/processing',
) {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route
          path="/textbooks/:textbookId/versions/:versionId/processing"
          element={
            <>
              <BookProcessingPage />
              <LocationProbe />
            </>
          }
        />
      </Routes>
    </MemoryRouter>,
  );
}

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location">{location.search}</div>;
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
  state.progress = null;
  state.progressCalls = [];
  state.cancelPending = false;
  state.create.mockReset().mockResolvedValue({
    generation_job_id: 'job-1',
    version_id: 'version-1',
    scope: 'book_pipeline',
    status: 'queued',
    attempt_count: 0,
    pause_after_chapter_analysis: false,
    reused_existing_job: false,
  });
  state.cancel.mockReset().mockResolvedValue({
    generation_job_id: 'job-1',
    version_id: 'version-1',
    scope: 'book_pipeline',
    status: 'running',
    attempt_count: 1,
    pause_after_chapter_analysis: false,
    reused_existing_job: false,
  });
  vi.spyOn(globalThis.crypto, 'randomUUID').mockReturnValue(
    'ba8a3e5c-c0b4-4a40-95ec-349310992445',
  );
});

const progress = {
  job_id: 'job-1',
  status: 'running',
  last_sequence: 41,
  stages: [
    {
      name: 'chapter_analysis',
      label: '教材章节解析',
      status: 'completed',
      current: 1,
      total: 12,
      events: [],
    },
    {
      name: 'content_processing',
      label: '内容智能处理',
      status: 'running',
      current: 2,
      total: 12,
      events: [
        { sequence: 2, label: '已完成：Unit 1', status: 'completed' },
        {
          sequence: 3,
          label: '正在生成 Reading A 知识稿',
          detail: '正在提取术语',
          status: 'running',
        },
      ],
    },
    {
      name: 'knowledge_point_generation',
      label: '知识点生成',
      status: 'completed',
      current: 22,
      total: 22,
      events: [{ sequence: 4, label: '知识点候选已完成', status: 'completed' }],
    },
    {
      name: 'lesson_preparation',
      label: '课程制作',
      status: 'queued',
      current: null,
      total: null,
      events: [],
    },
  ],
};

describe('BookProcessingPage progress timeline', () => {
  it('renders four fixed stages and the persisted event labels', async () => {
    state.progress = progress;
    renderPage(
      '/textbooks/textbook-1/versions/version-1/processing?job=job-from-url',
    );

    expect(await screen.findByText('教材章节解析')).toBeInTheDocument();
    expect(screen.getByText('内容智能处理')).toBeInTheDocument();
    expect(screen.getByText('知识点生成')).toBeInTheDocument();
    expect(screen.getByText('课程制作')).toBeInTheDocument();
    expect(screen.getByText('正在生成 Reading A 知识稿')).toBeInTheDocument();
    expect(screen.getByText('已完成：Unit 1')).toBeInTheDocument();
    expect(screen.getByText('进行中：Unit 2 / 共 12 个')).toBeInTheDocument();
    expect(screen.getByText('待处理：Unit 3 - Unit 12')).toBeInTheDocument();
    expect(screen.getByText('已完成 22 个候选')).toBeInTheDocument();
    expect(screen.getByText('等待知识点确认')).toBeInTheDocument();
    expect(state.progressCalls).toContainEqual(['job-from-url', true]);
  });

  it('does not render unsafe event payload fields', async () => {
    state.progress = {
      ...progress,
      stages: progress.stages.map((stage) => ({
        ...stage,
        events: stage.events.map((event) => ({
          ...event,
          reasoning: 'PRIVATE_CHAIN_OF_THOUGHT',
          tool_result: 'PRIVATE_TOOL_RESULT',
        })),
      })),
    };
    renderPage(
      '/textbooks/textbook-1/versions/version-1/processing?job=job-from-url',
    );

    expect(await screen.findByText('内容智能处理')).toBeInTheDocument();
    expect(screen.queryByText('PRIVATE_CHAIN_OF_THOUGHT')).not.toBeInTheDocument();
    expect(screen.queryByText('PRIVATE_TOOL_RESULT')).not.toBeInTheDocument();
  });

  it('offers cancellation while the job is active', async () => {
    state.progress = progress;
    renderPage(
      '/textbooks/textbook-1/versions/version-1/processing?job=job-from-url',
    );

    expect(
      await screen.findByRole('button', { name: '取消处理' }),
    ).toBeEnabled();
  });

  it('submits cancellation once and shows the pending state', async () => {
    state.progress = progress;
    let resolveCancel: ((value: unknown) => void) | undefined;
    state.cancel.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveCancel = resolve;
        }),
    );
    renderPage(
      '/textbooks/textbook-1/versions/version-1/processing?job=job-from-url',
    );
    const user = userEvent.setup();

    await user.click(await screen.findByRole('button', { name: '取消处理' }));
    const dialog = await screen.findByRole('dialog');
    const confirm = within(dialog).getByRole('button', {
      name: '确认取消处理',
    });

    fireEvent.click(confirm);
    fireEvent.click(confirm);

    await waitFor(() => expect(state.cancel).toHaveBeenCalledTimes(1));
    expect(state.cancel).toHaveBeenCalledWith('job-from-url');
    expect(confirm).toBeDisabled();

    resolveCancel?.({
      generation_job_id: 'job-from-url',
      version_id: 'version-1',
      scope: 'book_pipeline',
      status: 'running',
      attempt_count: 1,
      pause_after_chapter_analysis: false,
      reused_existing_job: false,
    });

    const cancelling = await screen.findByRole('button', {
      name: '正在取消',
    });
    expect(cancelling).toBeDisabled();
  });

  it('hides cancellation for a terminal job', async () => {
    state.progress = { ...progress, status: 'completed' };
    renderPage(
      '/textbooks/textbook-1/versions/version-1/processing?job=job-from-url',
    );

    expect(await screen.findByText('教材章节解析')).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: '取消处理' }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: '正在取消' }),
    ).not.toBeInTheDocument();
  });

  it('shows the terminal job failure separately from completed stages', async () => {
    state.progress = {
      ...progress,
      status: 'failed',
      error_code: 'managed_book_pipeline_invalid',
      error_message: '教材智能处理结果不完整、格式无效或资产校验失败，请重新运行。',
    };
    renderPage(
      '/textbooks/textbook-1/versions/version-1/processing?job=job-from-url',
    );

    expect(await screen.findByText('处理失败')).toBeInTheDocument();
    expect(
      screen.getByText(
        '教材智能处理结果不完整、格式无效或资产校验失败，请重新运行。',
      ),
    ).toBeInTheDocument();
    expect(screen.getByText('已完成')).toBeInTheDocument();
  });
});

describe('BookProcessingPage processing brief', () => {
  it('stores the created job id in the URL for refresh recovery', async () => {
    const { dialog } = await openDialog();

    await userEvent
      .setup()
      .click(within(dialog).getByRole('button', { name: '开始处理' }));

    await waitFor(() =>
      expect(screen.getByTestId('location')).toHaveTextContent('?job=job-1'),
    );
    expect(state.progressCalls).toContainEqual(['job-1', true]);
  });

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

    expect(await screen.findByText('正在处理')).toBeInTheDocument();
    await userEvent
      .setup()
      .click(screen.getByRole('button', { name: '开始处理' }));
    const reopened = await screen.findByRole('dialog');
    expect(
      within(reopened).getByRole('button', { name: '开始处理' }),
    ).toBeEnabled();
  });
});
