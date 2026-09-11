import { describe, it, expect } from 'vitest';
import { PRESETS_META, getPreset, type PresetId } from '../presets';
import { getWidget } from '../framework/WidgetRegistry';
import { BREAKPOINT_KEYS, COLS } from '../framework/gridConstants';
import '../index';

const PRESET_IDS = PRESETS_META.map((preset) => preset.id);

describe('dashboard presets', () => {
  it('exposes metadata for every preset it can build', () => {
    expect(PRESET_IDS).toEqual(['family-desk', 'homework-focus']);
    for (const meta of PRESETS_META) {
      // Every render site resolves these through t(), so a missing one is a
      // blank label rather than a crash.
      for (const key of [meta.nameKey, meta.tagKey, meta.descriptionKey, meta.bestForKey]) {
        expect(key.startsWith('dashboard.widgets.presets.')).toBe(true);
      }
      expect(meta.pillKeys.length).toBeGreaterThan(0);
    }
  });

  it('every widget type a preset references is registered', () => {
    // REGRESSION-CRITICAL: this is the failure the whole restore is prone to.
    // A preset that names a widget nobody registers renders an empty cell, and
    // the user sees a hole in their brand-new dashboard with no error.
    for (const id of PRESET_IDS) {
      const preset = getPreset(id as PresetId);
      expect(preset.widgets.length).toBeGreaterThan(0);
      for (const widget of preset.widgets) {
        expect(getWidget(widget.type), `preset ${id} references unregistered ${widget.type}`)
          .toBeDefined();
      }
    }
  });

  it("every preset's defaultConfig satisfies its widget's schema", () => {
    for (const id of PRESET_IDS) {
      const preset = getPreset(id as PresetId);
      for (const widget of preset.widgets) {
        const def = getWidget(widget.type);
        if (!def?.configSchema) continue;
        const result = def.configSchema.safeParse(widget.config);
        expect(
          result.success,
          `preset ${id}'s config for ${widget.type} fails its own schema`,
        ).toBe(true);
      }
    }
  });

  it('gives every widget a layout entry at every breakpoint', () => {
    for (const id of PRESET_IDS) {
      const preset = getPreset(id as PresetId);
      for (const bp of BREAKPOINT_KEYS) {
        const items = preset.layouts[bp] ?? [];
        const placed = new Set(items.map((item) => item.i));
        for (const widget of preset.widgets) {
          expect(placed.has(widget.id), `preset ${id} leaves ${widget.id} unplaced at ${bp}`).toBe(
            true,
          );
        }
      }
    }
  });

  it('keeps every cell inside the grid', () => {
    for (const id of PRESET_IDS) {
      const preset = getPreset(id as PresetId);
      for (const bp of BREAKPOINT_KEYS) {
        for (const item of preset.layouts[bp] ?? []) {
          expect(item.x).toBeGreaterThanOrEqual(0);
          expect(item.x + item.w).toBeLessThanOrEqual(COLS);
          expect(item.w).toBeGreaterThan(0);
          expect(item.h).toBeGreaterThan(0);
        }
      }
    }
  });

  it('gives every preset widget a unique id', () => {
    for (const id of PRESET_IDS) {
      const preset = getPreset(id as PresetId);
      const ids = preset.widgets.map((widget) => widget.id);
      expect(new Set(ids).size).toBe(ids.length);
    }
  });
});
