import { useMemo } from 'react';
import { getPreset, type PresetId } from '../../presets';
import type { RGLItem, WidgetInstance } from '../../types';

/**
 * Schematic preview of a preset's layout: a proportional grid of cells, each
 * carrying a small motif so the four widget families read differently at a
 * glance.
 *
 * Upstream's version was 712 lines because it hand-drew a signature glyph for
 * each of the thirty finance widgets (candles, heatmap blocks, ticker tapes).
 * Only four families exist here, so the glyph layer is a short switch rather
 * than a library — the point of a thumbnail is the *layout*, and the motif only
 * has to say which kind of thing sits in each cell.
 */
const C = {
  bg: '#F3EEE8',
  paper: '#FDFBF6',
  paperHi: '#FFFBF0',
  line: '#E6DFD2',
  ink: '#17150F',
  inkSoft: '#47423A',
  inkMute: '#8A8377',
  accent: '#0F3D2E',
  accentSoft: '#DBE8DF',
  highlight: '#F7D76A',
  chinese: '#D95D39',
  math: '#277DA1',
  english: '#6A994E',
};

interface CellVisuals {
  bg: string;
  stroke?: string;
}

const TYPE_VISUALS: Record<string, CellVisuals> = {
  'education.homeworkCalendar': { bg: C.paperHi, stroke: C.line },
  'agent.conversation': { bg: C.highlight, stroke: C.line },
  'threads.recent': { bg: C.paper, stroke: C.line },
  'workspace.picker': { bg: C.accentSoft },
  'automations.list': { bg: C.paper, stroke: C.line },
};

const DEFAULT_VISUALS: CellVisuals = { bg: C.paper, stroke: C.line };

/** List rows: a subject dot plus a bar of "text". */
function ListMotif({ x, y, w, h, colors }: { x: number; y: number; w: number; h: number; colors: string[] }) {
  const rows = Math.max(1, Math.min(5, Math.floor((h - 8) / 9)));
  const barW = Math.max(6, w - 22);
  return (
    <g>
      {Array.from({ length: rows }, (_, i) => {
        const rowY = y + 6 + i * 9;
        return (
          <g key={i}>
            <circle cx={x + 8} cy={rowY + 2.5} r={2} fill={colors[i % colors.length]} />
            <rect
              x={x + 14}
              y={rowY}
              width={barW * (i % 2 ? 0.7 : 1)}
              height={3}
              rx={1.5}
              fill={C.inkMute}
              opacity={0.55}
            />
            <rect
              x={x + 14}
              y={rowY + 5}
              width={barW * 0.35}
              height={2}
              rx={1}
              fill={C.inkMute}
              opacity={0.3}
            />
          </g>
        );
      })}
    </g>
  );
}

/** A rounded input pill with a send mark. */
function ConversationMotif({ x, y, w, h }: { x: number; y: number; w: number; h: number }) {
  const pillW = Math.max(12, w - 16);
  const pillH = Math.min(12, Math.max(7, h / 3));
  const pillY = y + Math.max(4, (h - pillH) / 2);
  return (
    <g>
      <rect x={x + 8} y={pillY} width={pillW} height={pillH} rx={pillH / 2} fill={C.ink} opacity={0.14} />
      <circle cx={x + 8 + pillW - pillH / 2} cy={pillY + pillH / 2} r={pillH / 2 - 1.5} fill={C.accent} />
    </g>
  );
}

/** Tiled squares, suggesting a set of places to go. */
function PickerMotif({ x, y, w, h }: { x: number; y: number; w: number; h: number }) {
  const size = 7;
  const gap = 3;
  const cols = Math.max(1, Math.floor((w - 12 + gap) / (size + gap)));
  const rows = Math.max(1, Math.min(3, Math.floor((h - 10 + gap) / (size + gap))));
  return (
    <g>
      {Array.from({ length: rows * cols }, (_, i) => (
        <rect
          key={i}
          x={x + 6 + (i % cols) * (size + gap)}
          y={y + 6 + Math.floor(i / cols) * (size + gap)}
          width={size}
          height={size}
          rx={1.5}
          fill={C.accent}
          opacity={0.35}
        />
      ))}
    </g>
  );
}

function WidgetGlyph({
  type,
  x,
  y,
  w,
  h,
}: {
  type: string;
  x: number;
  y: number;
  w: number;
  h: number;
}) {
  if (w < 18 || h < 14) return null;
  if (type === 'education.homeworkCalendar') {
    return <ListMotif x={x} y={y} w={w} h={h} colors={[C.chinese, C.math, C.english]} />;
  }
  if (type === 'threads.recent') {
    return <ListMotif x={x} y={y} w={w} h={h} colors={[C.inkMute, C.inkMute, C.inkMute]} />;
  }
  if (type === 'agent.conversation') return <ConversationMotif x={x} y={y} w={w} h={h} />;
  if (type === 'workspace.picker') return <PickerMotif x={x} y={y} w={w} h={h} />;
  if (type === 'automations.list') {
    return <ListMotif x={x} y={y} w={w} h={h} colors={[C.accent, C.accent, C.accent]} />;
  }
  return null;
}

interface LayoutProps {
  widgets: WidgetInstance[];
  layouts: RGLItem[];
}

function PresetLayoutThumbnail({ widgets, layouts }: LayoutProps) {
  const VIEW_W = 300;
  const VIEW_H = 190;
  const PAD = 4;
  const GRID_COLS = 12;
  const innerW = VIEW_W - PAD * 2;
  const innerH = VIEW_H - PAD * 2;
  const maxRow = Math.max(1, ...layouts.map((l) => l.y + l.h));
  const colW = innerW / GRID_COLS;
  const rowH = innerH / maxRow;
  const widgetsById = new Map(widgets.map((w) => [w.id, w]));

  return (
    <svg viewBox={`0 0 ${VIEW_W} ${VIEW_H}`} className="block w-full" aria-hidden>
      <rect x={0} y={0} width={VIEW_W} height={VIEW_H} fill={C.bg} />
      {layouts.map((l) => {
        const widget = widgetsById.get(l.i);
        if (!widget) return null;
        const visuals = TYPE_VISUALS[widget.type] ?? DEFAULT_VISUALS;
        const rx = PAD + l.x * colW + 1;
        const ry = PAD + l.y * rowH + 1;
        const rw = l.w * colW - 2;
        const rh = l.h * rowH - 2;
        return (
          <g key={l.i}>
            <rect
              x={rx}
              y={ry}
              width={rw}
              height={rh}
              rx={3}
              fill={visuals.bg}
              stroke={visuals.stroke ?? 'none'}
              strokeWidth={visuals.stroke ? 1 : 0}
            />
            <WidgetGlyph type={widget.type} x={rx} y={ry} w={rw} h={rh} />
          </g>
        );
      })}
    </svg>
  );
}

export function PresetThumbnail({ id }: { id: PresetId }) {
  const preset = useMemo(() => getPreset(id), [id]);
  return <PresetLayoutThumbnail widgets={preset.widgets} layouts={preset.layouts.lg ?? []} />;
}
