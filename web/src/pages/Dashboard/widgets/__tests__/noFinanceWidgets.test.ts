import { describe, it, expect } from 'vitest';
import '../index';
import { listWidgets, listWidgetsByCategory } from '../framework/WidgetRegistry';

/**
 * The canvas is the upstream layout system with this branch's widgets in it.
 * The finance definitions the layout used to host were removed on purpose in
 * `37fef0e9`; this is the guard that they do not come back by accident — a
 * re-registered widget would also drag its API, its tools and its locale copy
 * back in.
 */
const RETIRED_TYPES = [
  'markets.overview',
  'markets.miniChartGrid',
  'chart.symbol',
  'news.feed',
  'insight.brief',
  'calendar.earnings',
  'portfolio.holdings',
  'watchlist.list',
  'personal.portfolioWatchlist',
];

describe('dashboard widget registry', () => {
  it('registers no retired finance widget', () => {
    const types = listWidgets().map((widget) => widget.type);
    expect(types.filter((type) => RETIRED_TYPES.includes(type))).toEqual([]);
  });

  it('registers no TradingView embed', () => {
    expect(listWidgets().map((widget) => widget.type).filter((t) => t.startsWith('tv.'))).toEqual(
      [],
    );
  });

  it('registers only categories this branch can render', () => {
    // A 'markets' or 'intel' tab in the gallery would be empty by construction,
    // and those categories only ever existed to hold finance widgets.
    expect(Object.keys(listWidgetsByCategory()).sort()).toEqual(['agent', 'personal', 'workspace']);
  });

  it('registers the homework calendar under the personal category', () => {
    const homework = listWidgets().find((widget) => widget.type === 'education.homeworkCalendar');
    expect(homework?.category).toBe('personal');
  });
});
