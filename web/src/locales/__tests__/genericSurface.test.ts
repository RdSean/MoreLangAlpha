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
  it('keeps the workspace overview and the widget canvas in the dashboard namespace', () => {
    // The dashboard is two surfaces: the classic workspace overview, and the
    // widget canvas restored from upstream, plus the control that switches
    // between them. Nothing else belongs in the namespace — a
    // `dashboard.market*` block would mean a finance widget crept back in.
    expect(Object.keys(enUS.dashboard)).toEqual(['overview', 'widgets', 'layoutToggle']);
    expect(Object.keys(zhCN.dashboard)).toEqual(['overview', 'widgets', 'layoutToggle']);
  });

  it('keeps the canvas free of finance widget copy', () => {
    // The layout framework came back; the finance widgets it used to host did
    // not. A locale key for one of those widgets is the earliest sign that one
    // is being re-registered, so assert the subtrees are gone by name.
    const retiredWidgetLocales = [
      'marketsOverview', 'newsFeed', 'earningsCalendar', 'watchlist',
      'portfolio', 'portfolioWatchlist', 'insightBrief', 'miniChartGrid',
      'chart', 'holdings', 'tickerTape', 'stockHeatmap', 'cryptoHeatmap',
      'forexHeatmap', 'etfHeatmap', 'economicEvents', 'economicMap',
      'technicals', 'movers', 'symbolSpotlight', 'singleTicker', 'symbolInfo',
      'companyProfile', 'companyFinancials', 'stockScreener',
      'cryptoScreener', 'topStories',
    ];
    for (const key of retiredWidgetLocales) {
      expect(enUS.dashboard.widgets).not.toHaveProperty(key);
      expect(zhCN.dashboard.widgets).not.toHaveProperty(key);
    }
  });

  it('does not ship retired market or onboarding locale namespaces', () => {
    expect(enUS).not.toHaveProperty('marketView');
    expect(enUS).not.toHaveProperty('onboarding');
    expect(zhCN).not.toHaveProperty('marketView');
    expect(zhCN).not.toHaveProperty('onboarding');
  });

  it('does not retain financial product language in either catalog', () => {
    // The brokerage consent dialog is the one deliberate exception: its
    // capability groups name what a connection may do, so `watchlists` and
    // `alerts` have to say so. Everything else stays out — a retired market
    // surface must not creep back in through a label.
    const withoutBrokerageConsent = (catalog: unknown) => {
      const clone = structuredClone(catalog) as {
        plugins?: { brokerages?: { capabilities?: unknown } };
      };
      if (clone.plugins?.brokerages) delete clone.plugins.brokerages.capabilities;
      return JSON.stringify(clone);
    };
    expect(withoutBrokerageConsent(enUS)).not.toMatch(/TradingView|Watchlist|Price Alert|MarketView|market watch|SEC filings|Stock Prices|Options chain|Pre-Market|Portfolio/i);
    expect(withoutBrokerageConsent(zhCN)).not.toMatch(/TradingView|自选股|投资组合|价格提醒|财报|证券文件|实时行情|市场总览|股票价格|期权链|盘前|持仓/);
  });

  it('does not retain retired financial packages or E2E response fixtures', () => {
    // `react-grid-layout` is deliberately NOT in this list: it is a pure
    // layout library that the restored dashboard canvas needs, with no market
    // data behind it. The charting libraries stay out.
    expect(Object.keys(packageJson.dependencies)).not.toEqual(
      expect.arrayContaining(['lightweight-charts', 'recharts']),
    );
    expect(e2eMockSource).not.toMatch(
      /market-data|watchlist|portfolio|calendar\/earnings|sampleNewsArticle|sampleIndexSnapshot/i,
    );
  });
});
