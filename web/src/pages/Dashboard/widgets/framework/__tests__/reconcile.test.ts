import { describe, it, expect } from 'vitest';
import { LayoutGrid } from 'lucide-react';
import { reconcileLayouts, placeAtBottom } from '../reconcile';
import { registerWidget } from '../WidgetRegistry';
import '../../index'; // Register all widgets so getWidget() returns definitions.

// Upstream asserted the clamp and min/max-fill behaviour through the finance
// widget definitions (markets.overview had maxH=11, news.feed carried a
// min/max pair, agent.conversation is fit-to-content). Those widgets are not in
// this branch, so the same three shapes are declared here. The behaviour under
// test belongs to `reconcileLayouts`, not to any particular widget.
const base = {
  titleKey: 'fixture.title',
  category: 'personal' as const,
  icon: LayoutGrid,
  component: () => null,
};

/** Carries both a min and a max — the clamp fixture. */
registerWidget({
  ...base,
  type: 'fixture.bounded',
  defaultConfig: {},
  defaultSize: { w: 12, h: 11 },
  minSize: { w: 3, h: 5 },
  maxSize: { w: 12, h: 11 },
});

/** Carries a min only — the "fill in constraints" fixture. */
registerWidget({
  ...base,
  type: 'fixture.list',
  defaultConfig: {},
  defaultSize: { w: 4, h: 8 },
  minSize: { w: 3, h: 6 },
});

/** Drives the fit-to-content cell lock. */
registerWidget({
  ...base,
  type: 'fixture.fit',
  defaultConfig: {},
  defaultSize: { w: 8, h: 22 },
  minSize: { w: 3, h: 6 },
  fitToContent: true,
});

describe('reconcileLayouts', () => {
  it('drops layout entries whose widgets no longer exist', () => {
    const widgets = [{ id: 'w1', type: 'fixture.list', config: {} }];
    const layouts = {
      lg: [
        { i: 'w1', x: 0, y: 0, w: 4, h: 8 },
        { i: 'w_ghost', x: 4, y: 0, w: 4, h: 4 },
      ],
    };
    const out = reconcileLayouts(widgets, layouts);
    expect(out.lg).toHaveLength(1);
    expect(out.lg?.[0].i).toBe('w1');
  });

  it('auto-places widgets that have no layout entry at the bottom', () => {
    const widgets = [
      { id: 'w1', type: 'fixture.list', config: {} },
      { id: 'w2', type: 'fixture.bounded', config: {} },
    ];
    const layouts = {
      lg: [{ i: 'w1', x: 0, y: 0, w: 4, h: 8 }],
    };
    const out = reconcileLayouts(widgets, layouts);
    expect(out.lg).toHaveLength(2);
    const placed = out.lg?.find((l) => l.i === 'w2');
    expect(placed).toBeDefined();
    expect(placed!.y).toBeGreaterThanOrEqual(8);
  });

  it('produces both lg and md breakpoints', () => {
    const widgets = [{ id: 'w1', type: 'fixture.list', config: {} }];
    const out = reconcileLayouts(widgets, {});
    expect(out.lg).toHaveLength(1);
    expect(out.md).toHaveLength(1);
  });

  it('preserves explicit layout coords on reconcile', () => {
    const widgets = [{ id: 'w1', type: 'fixture.list', config: {} }];
    const layouts = { lg: [{ i: 'w1', x: 3, y: 5, w: 6, h: 20 }] };
    const out = reconcileLayouts(widgets, layouts);
    expect(out.lg?.[0]).toMatchObject({ i: 'w1', x: 3, y: 5, w: 6, h: 20 });
  });

  it('clamps stored w/h to the widget definition [min, max] range', () => {
    // fixture.bounded has maxH=11 and minW=3; a legacy record with h=33 and
    // w=2 should snap down to h=11 and up to w=3 so the widget doesn't render
    // huge.
    const widgets = [{ id: 'w1', type: 'fixture.bounded', config: {} }];
    const layouts = { lg: [{ i: 'w1', x: 0, y: 0, w: 2, h: 33 }] };
    const out = reconcileLayouts(widgets, layouts);
    expect(out.lg?.[0].h).toBe(11);
    expect(out.lg?.[0].w).toBe(3);
  });

  it('fills in min/max size constraints from the widget definition', () => {
    const widgets = [{ id: 'w1', type: 'fixture.list', config: {} }];
    const layouts = { lg: [{ i: 'w1', x: 0, y: 0, w: 4, h: 8 }] };
    const out = reconcileLayouts(widgets, layouts);
    expect(out.lg?.[0].minW).toBeDefined();
    expect(out.lg?.[0].minH).toBeDefined();
  });
});

describe('placeAtBottom', () => {
  it('places new items below existing content', () => {
    const layouts = { lg: [{ i: 'a', x: 0, y: 2, w: 4, h: 4 }] };
    const out = placeAtBottom(layouts, 'b', 6, 3);
    const placed = out.lg?.find((l) => l.i === 'b');
    expect(placed).toBeDefined();
    expect(placed!.y).toBe(6); // 2 + 4 = 6
    expect(placed!.w).toBe(6);
    expect(placed!.h).toBe(3);
  });
});

// Previously-uncovered branches in reconcileLayouts.
describe('reconcileLayouts — edge cases', () => {
  it('produces empty arrays for both breakpoints when widgets is empty', () => {
    const out = reconcileLayouts([], {});
    expect(out.lg).toEqual([]);
    expect(out.md).toEqual([]);
  });

  it('keeps a layout item whose widget type is not registered (no crash)', () => {
    const widgets = [{ id: 'w1', type: 'not.a.registered.type', config: {} }];
    const layouts = { lg: [{ i: 'w1', x: 0, y: 0, w: 4, h: 4 }] };
    const out = reconcileLayouts(widgets, layouts);
    // Entry is preserved unchanged — no clamp, no min/max fill-in — because
    // the registry can't provide bounds. Render path shows an empty cell.
    expect(out.lg).toHaveLength(1);
    expect(out.lg?.[0]).toMatchObject({ i: 'w1', x: 0, y: 0, w: 4, h: 4 });
  });

  it('preserves stored minH/maxH for fit-to-content widgets', () => {
    // fixture.fit registers with fitToContent: true. Reconcile must honor the
    // layout's stored min/max so DashboardGrid's fitHeight cell-lock is not
    // blown up on every save.
    const widgets = [{ id: 'w1', type: 'fixture.fit', config: {} }];
    const layouts = {
      lg: [{ i: 'w1', x: 0, y: 0, w: 8, h: 22, minH: 22, maxH: 22 }],
    };
    const out = reconcileLayouts(widgets, layouts);
    expect(out.lg?.[0].minH).toBe(22);
    expect(out.lg?.[0].maxH).toBe(22);
  });

  it('auto-places multiple new widgets without colliding on y', () => {
    const widgets = [
      { id: 'w1', type: 'fixture.list', config: {} },
      { id: 'w2', type: 'fixture.bounded', config: {} },
      { id: 'w3', type: 'fixture.fit', config: {} },
    ];
    const out = reconcileLayouts(widgets, {});
    const ys = out.lg?.map((l) => l.y) ?? [];
    // First at 0, subsequent ones at maxY of the previous — strictly
    // non-decreasing, and w2/w3 start at or below w1's bottom.
    expect(ys[0]).toBe(0);
    expect(ys[1]).toBeGreaterThanOrEqual(ys[0]);
    expect(ys[2]).toBeGreaterThanOrEqual(ys[1]);
  });
});
