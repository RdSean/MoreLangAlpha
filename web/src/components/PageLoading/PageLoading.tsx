import React from 'react';
import { useTranslation } from 'react-i18next';
import './PageLoading.css';

/**
 * The activity wall behind the loader. It is purely decorative and marked
 * aria-hidden; no workspace state is read or inferred here.
 */
const ACTIVITY_LABELS = [
  'WORKSPACE', 'THREADS', 'FILES', 'SKILLS', 'TOOLS', 'TASKS', 'MEMOS',
  'SANDBOX', 'AUTOMATIONS', 'CONTEXT', 'RESEARCH', 'NOTES', 'OUTPUTS',
];

/**
 * Rows must outsize any viewport (the component clips the excess): 120 rows
 * of ~560ch cover 4K in both axes at the 12px wall type size. A tiny seeded
 * LCG stands in for Math.random so the wall is identical on every render.
 */
function buildWall(): string {
  let seed = 11;
  const rand = () => {
    seed = (seed * 1103515245 + 12345) & 0x7fffffff;
    return seed / 0x7fffffff;
  };
  const tokens = ACTIVITY_LABELS.map((label) =>
    `${label} ${rand() < 0.5 ? 'READY' : 'SYNCED'}`
  );
  const rows: string[] = [];
  for (let r = 0; r < 120; r++) {
    const shift = (r * 7) % tokens.length;
    const rotated = tokens.slice(shift).concat(tokens.slice(0, shift));
    rows.push(rotated.concat(rotated, rotated).join('   ').slice(0, 560));
  }
  return rows.join('\n');
}

const WALL = buildWall();

interface PageLoadingProps {
  /**
   * `screen` (default) fills the viewport on the page background — for the
   * auth gates and top-level route Suspense. `pane` fills its parent with a
   * transparent background — for Suspense fallbacks inside the app shell,
   * where the layout already paints the background.
   */
  variant?: 'screen' | 'pane';
}

/**
 * Branded loading state: a dim activity wall with a scan band, in pure CSS so
 * it stays in the main bundle and mounts instantly while route chunks load.
 */
function PageLoading({ variant = 'screen' }: PageLoadingProps) {
  const { t } = useTranslation();
  return (
    <div
      className={`page-loading${variant === 'pane' ? ' page-loading--pane' : ''}`}
      role="status"
    >
      <div className="page-loading__wall" aria-hidden="true">
        {WALL}
      </div>
      <div className="page-loading__scan" aria-hidden="true">
        <div className="page-loading__scan-inner">{WALL}</div>
      </div>
      <div className="page-loading__center">
        <p className="page-loading__label">
          {t('common.loading')}
          <span className="page-loading__cursor" aria-hidden="true">
            ▉
          </span>
        </p>
      </div>
    </div>
  );
}

export default PageLoading;
