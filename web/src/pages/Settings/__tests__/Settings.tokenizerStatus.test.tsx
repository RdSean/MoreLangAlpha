import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import i18n from '@/i18n';

const api = vi.hoisted(() => ({
  getStatus: vi.fn(),
  retryDownload: vi.fn(),
}));

vi.mock('@/api/model', () => ({
  getTokenizerResourceStatus: api.getStatus,
  retryTokenizerVocabularyDownload: api.retryDownload,
}));

import { TokenizerStatusAlert } from '../components/TokenizerStatusAlert';

const readyStatus = {
  encoding: 'cl100k_base' as const,
  status: 'ready' as const,
  exact: true,
  error_code: null,
};

const approximateStatus = {
  encoding: 'cl100k_base' as const,
  status: 'approximate' as const,
  exact: false,
  error_code: 'vocabulary_download_failed',
};

function renderAlert() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return render(<TokenizerStatusAlert />, { wrapper: Wrapper });
}

beforeEach(async () => {
  vi.clearAllMocks();
  await i18n.changeLanguage('en-US');
});

describe('Settings tokenizer resource status', () => {
  it('hides the tokenizer alert when exact counting is ready', async () => {
    api.getStatus.mockResolvedValue(readyStatus);

    renderAlert();

    await waitFor(() => expect(api.getStatus).toHaveBeenCalledOnce());
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('shows a prominent localized alert while approximate counting is active', async () => {
    api.getStatus.mockResolvedValue(approximateStatus);
    await i18n.changeLanguage('zh-CN');

    renderAlert();

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('精确 Token 词表不可用');
    expect(alert).toHaveTextContent('当前使用近似 Token 计数');
    expect(screen.getByRole('button', { name: '重新下载词表' })).toBeEnabled();
  });

  it('disables retry while downloading and removes the alert on success', async () => {
    api.getStatus.mockResolvedValue(approximateStatus);
    let finishDownload: ((status: typeof readyStatus) => void) | undefined;
    api.retryDownload.mockImplementation(
      () => new Promise<typeof readyStatus>((resolve) => { finishDownload = resolve; }),
    );

    renderAlert();

    fireEvent.click(await screen.findByRole('button', { name: 'Download vocabulary again' }));

    expect(
      await screen.findByRole('button', { name: 'Downloading vocabulary...' }),
    ).toBeDisabled();
    finishDownload?.(readyStatus);
    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument());
    expect(api.retryDownload).toHaveBeenCalledOnce();
  });

  it('keeps the alert visible and shows a localized failure after retry fails', async () => {
    api.getStatus.mockResolvedValue(approximateStatus);
    api.retryDownload.mockRejectedValue(new Error('private server detail'));

    renderAlert();

    fireEvent.click(await screen.findByRole('button', { name: 'Download vocabulary again' }));

    const alert = await screen.findByRole('alert');
    await waitFor(() => {
      expect(alert).toHaveTextContent('Vocabulary download failed. Check the server network and cache permissions, then try again.');
    });
    expect(alert).not.toHaveTextContent('private server detail');
  });
});
