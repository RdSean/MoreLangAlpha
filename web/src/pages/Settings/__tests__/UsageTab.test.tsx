import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const getDocumentUsage = vi.fn();

vi.mock('@/pages/Documents/api', () => ({
  getDocumentUsage: (...args: unknown[]) => getDocumentUsage(...args),
}));

// Recharts measures its container; jsdom reports zero and renders nothing.
// The chart's own correctness is the library's business — what these tests
// check is when we render it at all, and what the numbers say.
vi.mock('recharts', async () => {
  const actual = await vi.importActual<Record<string, unknown>>('recharts');
  return {
    ...actual,
    ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
      <div data-testid="chart">{children}</div>
    ),
  };
});

import UsageTab from '../panels/UsageTab';

function renderTab() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: Infinity } },
  });
  return render(
    <QueryClientProvider client={client}>
      <UsageTab />
    </QueryClientProvider>,
  );
}

function usage(days: Array<Record<string, number | string>>) {
  return {
    range: '7d',
    totals: {
      pages: days.reduce((sum, day) => sum + Number(day.pages), 0),
      cost_cents: days.reduce((sum, day) => sum + Number(day.cost_cents), 0),
      conversions: days.length,
    },
    days,
  };
}

beforeEach(() => {
  getDocumentUsage.mockReset();
});

describe('UsageTab', () => {
  it('shows the server totals rather than summing the buckets itself', async () => {
    getDocumentUsage.mockResolvedValue(
      usage([
        { day: '2026-09-01', pages: 12, cost_cents: 24, conversions: 1 },
        { day: '2026-09-03', pages: 5, cost_cents: 10, conversions: 1 },
      ]),
    );

    renderTab();

    expect(await screen.findByText('17')).toBeInTheDocument();
    // 34 cents, formatted as money.
    expect(await screen.findByText(/\$0\.34/)).toBeInTheDocument();
  });

  it('renders a chart when there is activity', async () => {
    getDocumentUsage.mockResolvedValue(
      usage([{ day: '2026-09-01', pages: 3, cost_cents: 6, conversions: 1 }]),
    );

    renderTab();

    expect(await screen.findByTestId('chart')).toBeInTheDocument();
    expect(screen.queryByTestId('usage-empty')).not.toBeInTheDocument();
  });

  it('says nothing happened instead of drawing an empty chart frame', async () => {
    // An empty frame reads as a broken chart; the honest message is different.
    getDocumentUsage.mockResolvedValue(usage([]));

    renderTab();

    expect(await screen.findByTestId('usage-empty')).toBeInTheDocument();
    expect(screen.queryByTestId('chart')).not.toBeInTheDocument();
  });

  it('refetches with the range the user picked', async () => {
    getDocumentUsage.mockResolvedValue(usage([]));

    renderTab();
    await screen.findByTestId('usage-empty');
    expect(getDocumentUsage).toHaveBeenCalledWith('7d');

    fireEvent.click(screen.getByTestId('usage-range-30d'));

    expect(await screen.findByTestId('usage-empty')).toBeInTheDocument();
    expect(getDocumentUsage).toHaveBeenLastCalledWith('30d');
  });

  it('marks the active range', async () => {
    getDocumentUsage.mockResolvedValue(usage([]));

    renderTab();
    await screen.findByTestId('usage-empty');

    expect(screen.getByTestId('usage-range-7d')).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByTestId('usage-range-30d')).toHaveAttribute('aria-pressed', 'false');

    fireEvent.click(screen.getByTestId('usage-range-14d'));
    expect(screen.getByTestId('usage-range-14d')).toHaveAttribute('aria-pressed', 'true');
  });
});
