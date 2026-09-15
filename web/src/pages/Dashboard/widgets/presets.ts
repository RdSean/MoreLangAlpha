import { newWidgetId } from './framework/ids';
import type { DashboardPrefs, RGLItem, WidgetInstance } from './types';
import { DASHBOARD_PREFS_VERSION } from './types';

/**
 * Preset layouts for the family dashboard.
 *
 * Upstream shipped six finance presets (morning brief, researcher, trader,
 * portfolio steward, agent desk, TradingView workstation). This branch keeps
 * the machinery — the same `PresetId` / `PresetMeta` / `getPreset` /
 * `PRESETS_META` shape the prefs layer, the gallery and the thumbnails all
 * compile against — and replaces the contents with layouts built from the
 * widgets that actually exist here.
 */
export type PresetId = 'family-desk' | 'homework-focus';

export interface PresetMeta {
  id: PresetId;
  popular?: boolean;
  /** i18n keys for the user-facing chrome. Required — render sites resolve
   *  via `t(key)`. Use a `dashboard.widgets.presets.<id>.<field>` shape so
   *  `keys.test.ts` picks them up automatically. */
  nameKey: string;
  tagKey: string;
  descriptionKey: string;
  bestForKey: string;
  /** Per-pill i18n keys; pill count is determined by this array's length. */
  pillKeys: string[];
}

const newId = newWidgetId;

function makePrefs(
  widgets: WidgetInstance[],
  layoutsLg: RGLItem[],
): Pick<DashboardPrefs, 'widgets' | 'layouts' | 'version'> {
  return {
    version: DASHBOARD_PREFS_VERSION,
    widgets,
    layouts: { lg: layoutsLg, md: layoutsLg },
  };
}

/**
 * FAMILY DESK — the default.
 *
 * The homework calendar anchors the right rail so what is due stays visible
 * however far the left column scrolls. Recent conversations lead, because the
 * common visit is "carry on with what we were doing", and the workbench and
 * automations sit under them for starting something new.
 */
export function familyDeskPreset(): Pick<DashboardPrefs, 'widgets' | 'layouts' | 'version'> {
  const homework = { id: newId('hw'), type: 'education.homeworkCalendar', config: { window: '2w', showCompleted: false } };
  const conversation = { id: newId('ag'), type: 'agent.conversation', config: {} };
  const threads = { id: newId('th'), type: 'threads.recent', config: { workspaceId: 'all', limit: 10 } };
  const workspaces = { id: newId('wp'), type: 'workspace.picker', config: { limit: 8 } };
  const automations = { id: newId('au'), type: 'automations.list', config: { limit: 8 } };

  const widgets = [homework, conversation, threads, workspaces, automations];
  const layouts: RGLItem[] = [
    { i: homework.id, x: 8, y: 0, w: 4, h: 30 },
    { i: conversation.id, x: 0, y: 0, w: 8, h: 14 },
    { i: threads.id, x: 0, y: 14, w: 8, h: 22 },
    { i: workspaces.id, x: 0, y: 36, w: 4, h: 16 },
    { i: automations.id, x: 4, y: 36, w: 4, h: 20 },
  ];
  return makePrefs(widgets, layouts);
}

/**
 * HOMEWORK FOCUS — the calendar across the full width, with the workbench
 * underneath for "help with this one" and recent conversations alongside.
 */
export function homeworkFocusPreset(): Pick<DashboardPrefs, 'widgets' | 'layouts' | 'version'> {
  const homework = { id: newId('hw'), type: 'education.homeworkCalendar', config: { window: '1w', showCompleted: true } };
  const conversation = { id: newId('ag'), type: 'agent.conversation', config: {} };
  const threads = { id: newId('th'), type: 'threads.recent', config: { workspaceId: 'all', limit: 8 } };

  const widgets = [homework, conversation, threads];
  const layouts: RGLItem[] = [
    { i: homework.id, x: 0, y: 0, w: 12, h: 24 },
    { i: conversation.id, x: 0, y: 24, w: 8, h: 14 },
    { i: threads.id, x: 8, y: 24, w: 4, h: 24 },
  ];
  return makePrefs(widgets, layouts);
}

export const PRESETS_META: PresetMeta[] = [
  {
    id: 'family-desk',
    popular: true,
    nameKey: 'dashboard.widgets.presets.family-desk.name',
    tagKey: 'dashboard.widgets.presets.family-desk.tag',
    descriptionKey: 'dashboard.widgets.presets.family-desk.description',
    bestForKey: 'dashboard.widgets.presets.family-desk.bestFor',
    pillKeys: [
      'dashboard.widgets.presets.family-desk.pill1',
      'dashboard.widgets.presets.family-desk.pill2',
      'dashboard.widgets.presets.family-desk.pill3',
    ],
  },
  {
    id: 'homework-focus',
    nameKey: 'dashboard.widgets.presets.homework-focus.name',
    tagKey: 'dashboard.widgets.presets.homework-focus.tag',
    descriptionKey: 'dashboard.widgets.presets.homework-focus.description',
    bestForKey: 'dashboard.widgets.presets.homework-focus.bestFor',
    pillKeys: [
      'dashboard.widgets.presets.homework-focus.pill1',
      'dashboard.widgets.presets.homework-focus.pill2',
      'dashboard.widgets.presets.homework-focus.pill3',
    ],
  },
];

export function getPreset(id: PresetId): Pick<DashboardPrefs, 'widgets' | 'layouts' | 'version'> {
  switch (id) {
    case 'homework-focus':
      return homeworkFocusPreset();
    case 'family-desk':
    default:
      return familyDeskPreset();
  }
}
