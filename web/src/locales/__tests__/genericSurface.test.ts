import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import enUS from '../en-US.json';
import zhCN from '../zh-CN.json';

const packageJson = JSON.parse(
  readFileSync(resolve(process.cwd(), 'package.json'), 'utf-8'),
) as { dependencies: Record<string, string> };
const e2eMockSource = readFileSync(
  resolve(process.cwd(), 'e2e/helpers/mockResponses.js'),
  'utf-8',
);

describe('generic workspace locale boundary', () => {
  it('keeps only the workspace overview in the dashboard namespace', () => {
    expect(Object.keys(enUS.dashboard)).toEqual(['overview']);
    expect(Object.keys(zhCN.dashboard)).toEqual(['overview']);
  });

  it('does not ship retired market or onboarding locale namespaces', () => {
    expect(enUS).not.toHaveProperty('marketView');
    expect(enUS).not.toHaveProperty('onboarding');
    expect(zhCN).not.toHaveProperty('marketView');
    expect(zhCN).not.toHaveProperty('onboarding');
  });

  it('does not retain financial product language in either catalog', () => {
    expect(JSON.stringify(enUS)).not.toMatch(/TradingView|Watchlist|Price Alert|MarketView|market watch|SEC filings|Stock Prices|Options chain|Pre-Market|Portfolio/i);
    expect(JSON.stringify(zhCN)).not.toMatch(/TradingView|自选股|投资组合|价格提醒|财报|证券文件|实时行情|市场总览|股票价格|期权链|盘前|持仓/);
  });

  it('does not retain retired financial packages or E2E response fixtures', () => {
    expect(Object.keys(packageJson.dependencies)).not.toEqual(
      expect.arrayContaining(['lightweight-charts', 'react-grid-layout', 'recharts']),
    );
    expect(e2eMockSource).not.toMatch(
      /market-data|watchlist|portfolio|calendar\/earnings|sampleNewsArticle|sampleIndexSnapshot/i,
    );
  });
});
