import { describe, it, expect } from 'vitest';
import { z } from 'zod';
import { LayoutGrid } from 'lucide-react';
import { migrateDashboardPrefs } from '../migrations';
import { DASHBOARD_PREFS_VERSION } from '../../types';
import { registerWidget } from '../WidgetRegistry';
// Side-effect: load every widget definition so getWidget() returns schemas
// inside `sanitizeConfig`. Without this, the registry is empty and schemas
// silently no-op (the production app reaches the registry transitively via
// Dashboard → DashboardCustom; tests have to do it explicitly).
import '../../index';
import { getWidget, listWidgets } from '../WidgetRegistry';

// -----------------------------------------------------------------------------
// Fixtures
//
// Upstream exercised `sanitizeConfig` through the TradingView widget schemas —
// a ticker-tape symbol list, a forex currency list, a display-mode enum. Those
// widgets are not in this branch, but the generic recovery behaviour they were
// covering is: per-field `.catch()`, whole-config fallback, no-schema
// pass-through, and the array transform that drops invalid entries rather than
// fanning them out into duplicates. These fixtures keep that coverage attached
// to the framework instead of to a widget that happens to exist.
// -----------------------------------------------------------------------------

const SYMBOL_RE = /^[A-Z0-9._:-]+$/;

type EnumConfig = { mode: 'adaptive' | 'regular' | 'compact' };
registerWidget<EnumConfig>({
  type: 'fixture.enum',
  titleKey: 'fixture.enum',
  category: 'personal',
  icon: LayoutGrid,
  component: () => null,
  defaultConfig: { mode: 'adaptive' } satisfies EnumConfig,
  defaultSize: { w: 4, h: 6 },
  minSize: { w: 3, h: 4 },
  configSchema: z.object({
    mode: z.enum(['adaptive', 'regular', 'compact']).catch('adaptive'),
  }),
});

type FieldsConfig = { count: number; label: string };
registerWidget<FieldsConfig>({
  type: 'fixture.fields',
  titleKey: 'fixture.fields',
  category: 'personal',
  icon: LayoutGrid,
  component: () => null,
  defaultConfig: { count: 5, label: 'untitled' } satisfies FieldsConfig,
  defaultSize: { w: 4, h: 6 },
  minSize: { w: 3, h: 4 },
  configSchema: z.object({
    count: z.number().int().min(1).max(10).catch(5),
    label: z.string().min(1).catch('untitled'),
  }),
});

type ListConfig = { symbols: string[]; mode: 'adaptive' | 'regular' | 'compact' };
registerWidget<ListConfig>({
  type: 'fixture.list',
  titleKey: 'fixture.list',
  category: 'personal',
  icon: LayoutGrid,
  component: () => null,
  defaultConfig: { symbols: [], mode: 'compact' } satisfies ListConfig,
  defaultSize: { w: 6, h: 8 },
  minSize: { w: 3, h: 6 },
  configSchema: z.object({
    // Drop invalid entries (and dedupe) instead of per-element `.catch(default)`
    // — a corrupted blob with [bad, bad, NVDA] must become [NVDA] rather than
    // [SPY, SPY, NVDA] (silent duplication). The user keeps every valid symbol.
    symbols: z
      .array(z.unknown())
      .catch([])
      .transform((arr) => {
        const seen = new Set<string>();
        const out: string[] = [];
        for (const value of arr) {
          if (typeof value !== 'string') continue;
          if (!SYMBOL_RE.test(value) || value.length === 0) continue;
          if (seen.has(value)) continue;
          seen.add(value);
          out.push(value);
        }
        return out;
      }),
    mode: z.enum(['adaptive', 'regular', 'compact']).catch('compact'),
  }),
});

// A schema whose list field has a rich default: when every entry is bad the
// field must fall back to the whole default list, not to a one-element stub.
const RICH_DEFAULTS = ['USD', 'EUR', 'CNY', 'JPY', 'GBP', 'AUD', 'CAD', 'CHF', 'NZD'];
type RichDefaultConfig = { currencies: string[] };
registerWidget<RichDefaultConfig>({
  type: 'fixture.richdefault',
  titleKey: 'fixture.richdefault',
  category: 'personal',
  icon: LayoutGrid,
  component: () => null,
  defaultConfig: { currencies: RICH_DEFAULTS } satisfies RichDefaultConfig,
  defaultSize: { w: 4, h: 6 },
  minSize: { w: 3, h: 4 },
  configSchema: z.object({
    currencies: z
      .array(z.unknown())
      .catch([])
      .transform((arr) => {
        const valid = arr.filter(
          (value): value is string => typeof value === 'string' && /^[A-Z]{3}$/.test(value),
        );
        return valid.length ? valid : RICH_DEFAULTS;
      }),
  }),
});

// Registered with no schema on purpose — the back-compat branch must hold for
// widgets that opt out of config validation.
registerWidget<Record<string, never>>({
  type: 'fixture.noschema',
  titleKey: 'fixture.noschema',
  category: 'personal',
  icon: LayoutGrid,
  component: () => null,
  defaultConfig: {},
  defaultSize: { w: 4, h: 6 },
  minSize: { w: 3, h: 4 },
});

describe('migrateDashboardPrefs', () => {
  it('returns null for null / undefined / non-object input', () => {
    expect(migrateDashboardPrefs(null)).toBeNull();
    expect(migrateDashboardPrefs(undefined)).toBeNull();
    expect(migrateDashboardPrefs('not an object')).toBeNull();
    expect(migrateDashboardPrefs(42)).toBeNull();
  });

  it('renames legacy agent.input widget type to agent.conversation', () => {
    const out = migrateDashboardPrefs({
      widgets: [{ id: 'a', type: 'agent.input', config: {} }],
    });
    expect(out?.widgets[0].type).toBe('agent.conversation');
  });

  it('leaves non-legacy widget types untouched', () => {
    const out = migrateDashboardPrefs({
      widgets: [{ id: 'a', type: 'fixture.list', config: {} }],
    });
    expect(out?.widgets[0].type).toBe('fixture.list');
  });

  it('coerces non-array widgets to []', () => {
    const out = migrateDashboardPrefs({ widgets: 'not an array' as unknown });
    expect(out?.widgets).toEqual([]);
  });

  it('coerces array layouts to {}', () => {
    const out = migrateDashboardPrefs({ layouts: [] as unknown });
    expect(out?.layouts).toEqual({});
  });

  it('preserves valid layouts as-is', () => {
    const layouts = { lg: [{ i: 'a', x: 0, y: 0, w: 4, h: 4 }] };
    const out = migrateDashboardPrefs({ layouts });
    expect(out?.layouts).toEqual(layouts);
  });

  it("defaults unknown mode to 'classic'", () => {
    expect(migrateDashboardPrefs({ mode: 'bogus' as unknown })?.mode).toBe('classic');
    expect(migrateDashboardPrefs({})?.mode).toBe('classic');
  });

  it("honors explicit 'custom' mode", () => {
    expect(migrateDashboardPrefs({ mode: 'custom' })?.mode).toBe('custom');
  });

  it('always stamps the current version', () => {
    const out = migrateDashboardPrefs({ version: 0 as unknown, widgets: [] });
    expect(out?.version).toBe(DASHBOARD_PREFS_VERSION);
  });

  it('drops malformed history', () => {
    expect(migrateDashboardPrefs({ history: 'nope' as unknown })?.history).toBeUndefined();
  });

  it('preserves a valid history array', () => {
    const history = [{ widgets: [], layouts: {} }];
    expect(migrateDashboardPrefs({ history })?.history).toEqual(history);
  });

  // ---------------------------------------------------------------------------
  // layouts shape filter — per-breakpoint validation
  // ---------------------------------------------------------------------------
  describe('layouts per-breakpoint shape filter', () => {
    it('keeps real RGL arrays as-is', () => {
      const layouts = { lg: [{ i: 'a', x: 0, y: 0, w: 4, h: 4 }] };
      expect(migrateDashboardPrefs({ layouts })?.layouts).toEqual(layouts);
    });

    it('drops breakpoints whose value is an object instead of an array', () => {
      // Without the per-bp guard this passed straight through and crashed
      // reconcileLayouts (it `.filter()`s each breakpoint).
      const out = migrateDashboardPrefs({
        layouts: { lg: { foo: 'bar' }, md: [{ i: 'a', x: 0, y: 0, w: 4, h: 4 }] },
      });
      expect(out?.layouts.lg).toBeUndefined();
      expect(out?.layouts.md?.length).toBe(1);
    });

    it('drops breakpoints whose value is a primitive', () => {
      const out = migrateDashboardPrefs({
        layouts: { lg: 'garbage', md: 42, sm: null },
      });
      expect(out?.layouts).toEqual({});
    });
  });

  // ---------------------------------------------------------------------------
  // isValidWidgetInstance: shape filter
  // ---------------------------------------------------------------------------
  describe('widget instance shape filter', () => {
    it('drops null entries', () => {
      const out = migrateDashboardPrefs({
        widgets: [null, { id: 'a', type: 'fixture.list', config: {} }],
      });
      expect(out?.widgets.length).toBe(1);
      expect(out?.widgets[0].id).toBe('a');
    });

    it('drops string / number entries', () => {
      const out = migrateDashboardPrefs({
        widgets: ['garbage', 42, { id: 'a', type: 'fixture.list', config: {} }],
      });
      expect(out?.widgets.length).toBe(1);
    });

    it('drops entries missing an id', () => {
      const out = migrateDashboardPrefs({
        widgets: [
          { type: 'fixture.list', config: {} },
          { id: 'b', type: 'fixture.list', config: {} },
        ],
      });
      expect(out?.widgets.length).toBe(1);
      expect(out?.widgets[0].id).toBe('b');
    });

    it('drops entries missing a type or config', () => {
      const out = migrateDashboardPrefs({
        widgets: [
          { id: 'a', type: 'fixture.list' /* no config */ },
          { id: 'b', /* no type */ config: {} },
          { id: 'c', type: 'fixture.list', config: null /* invalid */ },
          { id: 'd', type: 'fixture.list', config: {} },
        ],
      });
      expect(out?.widgets.length).toBe(1);
      expect(out?.widgets[0].id).toBe('d');
    });
  });

  // ---------------------------------------------------------------------------
  // sanitizeConfig: per-widget Zod schema validation
  // ---------------------------------------------------------------------------
  describe('sanitizeConfig (Zod-driven)', () => {
    it('passes a valid config through unchanged', () => {
      const cfg = { symbols: ['NASDAQ:NVDA'], mode: 'compact' as const };
      const out = migrateDashboardPrefs({
        widgets: [{ id: 'a', type: 'fixture.list', config: cfg }],
      });
      expect(out?.widgets[0].config).toMatchObject(cfg);
    });

    it('coerces an unknown enum value via .catch()', () => {
      const out = migrateDashboardPrefs({
        widgets: [{ id: 'a', type: 'fixture.enum', config: { mode: 'foobar' } }],
      });
      expect((out?.widgets[0].config as { mode?: string }).mode).toBe('adaptive');
    });

    it('coerces bad field values to schema defaults via per-field .catch()', () => {
      // A non-empty object with one bogus field. Per-field `.catch(...)`
      // recovers on the SUCCESS branch — this exercises field-level recovery,
      // not the top-level fallback (covered in the next test).
      const out = migrateDashboardPrefs({
        widgets: [{ id: 'a', type: 'fixture.fields', config: { count: 'many' } }],
      });
      const def = getWidget('fixture.fields')?.defaultConfig as object;
      expect(out?.widgets[0].config).toMatchObject(def);
    });

    it('falls back to defaultConfig when top-level config shape is unparseable', () => {
      // Array config slips past the shape filter (typeof === 'object' and
      // !== null) but z.object().safeParse([]) fails at the top level — no
      // per-field .catch() can recover it. Sanitize must fall back to
      // defaultConfig wholesale.
      const out = migrateDashboardPrefs({
        widgets: [
          { id: 'a', type: 'fixture.fields', config: [] as unknown as Record<string, unknown> },
        ],
      });
      const def = getWidget('fixture.fields')?.defaultConfig as object;
      expect(out?.widgets[0].config).toEqual(def);
    });

    it('preserves widgets whose definition has no schema (back-compat)', () => {
      // Without the back-compat branch a schema-less widget would be reset to
      // its defaultConfig on every prefs load. `fixture.noschema` registers
      // without one.
      const out = migrateDashboardPrefs({
        widgets: [{ id: 'a', type: 'fixture.noschema', config: { freeform: true } }],
      });
      expect(out?.widgets[0].config).toEqual({ freeform: true });
    });

    it('preserves a config for a type the registry does not know', () => {
      const out = migrateDashboardPrefs({
        widgets: [{ id: 'a', type: 'made-up.no-schema', config: { freeform: true } }],
      });
      expect(out?.widgets[0].config).toEqual({ freeform: true });
    });

    it('rename happens BEFORE sanitize (legacy type uses new schema)', () => {
      // agent.input → agent.conversation. ConversationConfigSchema accepts {}.
      const out = migrateDashboardPrefs({
        widgets: [{ id: 'a', type: 'agent.input', config: {} }],
      });
      expect(out?.widgets[0].type).toBe('agent.conversation');
    });

    it('drops invalid symbols from array fields (no duplicate-default fallout)', () => {
      // Regression: per-element `.catch(default)` produced duplicates of the
      // catch default for every bad entry — `[bad, bad, AAPL]` became
      // `[SPY, SPY, AAPL]`. Now we drop bad entries instead.
      const out = migrateDashboardPrefs({
        widgets: [
          {
            id: 'a',
            type: 'fixture.list',
            config: {
              symbols: ['NASDAQ:NVDA', 'b@d sym', 42, null, 'NASDAQ:AAPL'],
              mode: 'compact',
            },
          },
        ],
      });
      const symbols = (out?.widgets[0].config as { symbols?: string[] }).symbols;
      expect(symbols).toEqual(['NASDAQ:NVDA', 'NASDAQ:AAPL']);
    });

    it('dedupes symbol arrays across the transform', () => {
      const out = migrateDashboardPrefs({
        widgets: [
          {
            id: 'a',
            type: 'fixture.list',
            config: { symbols: ['NVDA', 'NVDA', 'AAPL', 'NVDA'], mode: 'compact' },
          },
        ],
      });
      const symbols = (out?.widgets[0].config as { symbols?: string[] }).symbols;
      expect(symbols).toEqual(['NVDA', 'AAPL']);
    });

    it('list fields fall back to the full default list when all entries are bad', () => {
      const out = migrateDashboardPrefs({
        widgets: [
          {
            id: 'a',
            type: 'fixture.richdefault',
            config: { currencies: ['BAD1', 'BAD2', 42, null] },
          },
        ],
      });
      const currencies =
        (out?.widgets[0].config as { currencies?: string[] }).currencies ?? [];
      expect(currencies.length).toBeGreaterThanOrEqual(9);
      expect(currencies).toContain('USD');
      expect(currencies).toContain('CNY');
    });

    it('every registered widget can round-trip its own defaultConfig (no drift)', () => {
      // REGRESSION-CRITICAL: catches schema-vs-defaultConfig drift. Every
      // widget's defaultConfig MUST satisfy its own schema; otherwise users
      // who add a widget via the gallery would have it instantly clobbered.
      const types = listWidgets().map((d) => d.type);
      expect(types.length).toBeGreaterThan(0);
      for (const type of types) {
        const def = getWidget(type)!;
        if (!def.configSchema) continue;
        const result = def.configSchema.safeParse(def.defaultConfig);
        expect(result.success, `defaultConfig for ${type} failed schema parse`).toBe(true);
      }
    });
  });
});
