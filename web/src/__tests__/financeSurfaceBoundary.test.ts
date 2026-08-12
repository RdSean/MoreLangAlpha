import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import { describe, expect, it } from 'vitest';

const sourceRoot = join(process.cwd(), 'src');
const retiredFiles = [
  'pages/Login/MarketScanlines.tsx',
  'pages/Login/emberBall.ts',
  'pages/Login/spxSeries.ts',
  'pages/Login/EdgeGrain.tsx',
  'pages/Login/loginPaper.ts',
  'types/market.ts',
];
const financeOnlyTerms = [
  /market_watch/i,
  /market-watch/i,
  /market_data/i,
  /sec_filing/i,
  /portfolio/i,
  /watchlist/i,
  /price_trigger/i,
  /stock_prices/i,
  /market_indices/i,
  /sector_performance/i,
  /chart_annotation/i,
  /TradingView/i,
  /Lightweight Charts/i,
  /MarketView/i,
  /investment_preference/i,
  /EarningsEntry/i,
  /Equity Research/i,
  /Wrong ticker or company/i,
  /quote wall/i,
  /ticker-tape/i,
  /\b(?:AAPL|NVDA|SPX)\b/,
];

function runtimeSourceFiles(directory: string): string[] {
  return readdirSync(directory).flatMap((entry) => {
    const path = join(directory, entry);
    if (statSync(path).isDirectory()) {
      return entry === '__tests__' ? [] : runtimeSourceFiles(path);
    }
    return /\.(?:ts|tsx|css)$/.test(entry) ? [path] : [];
  });
}

describe('finance surface boundary', () => {
  it('removes finance-only modules and runtime product terms', () => {
    const remainingFiles = retiredFiles.filter((path) => existsSync(join(sourceRoot, path)));
    const remainingTerms = runtimeSourceFiles(sourceRoot)
      .filter((path) => financeOnlyTerms.some((term) => term.test(readFileSync(path, 'utf8'))))
      .map((path) => relative(sourceRoot, path));

    expect(remainingFiles).toEqual([]);
    expect(remainingTerms).toEqual([]);
  });
});
