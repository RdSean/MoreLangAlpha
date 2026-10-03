import { useLayoutEffect, useRef } from 'react';
import type React from 'react';
import { z } from 'zod';
import { registerAuthReset } from '@/lib/authResets';

/**
 * Session-scoped scroll positions keyed by a stable id (route path, thread id).
 * Module-level so positions survive route unmounts — the whole point: coming
 * back to a tab or thread lands where the user left, not at top/bottom.
 * `'bottom'` is a sticky sentinel: "the user was at the bottom", which for
 * growing content (chat) means re-pin to the new bottom, not a pixel offset.
 */
const positions = new Map<string, number | 'bottom'>();

// LRU bound for long-lived sessions (dashboards left open for days): route/page
// keys are finite, but thread keys accrue per thread visited. Entries are tiny;
// the cap is hygiene, not memory pressure. Deleted threads/workspaces also
// forget their keys eagerly at the delete sites.
const MAX_ENTRIES = 300;
const STORAGE_KEY = 'langalpha:reader-scroll:v1';
const MAX_STORAGE_LENGTH = 200_000;
const storedPositionsSchema = z.array(z.tuple([
  z.string().min(1).max(512),
  z.union([z.number().finite().nonnegative(), z.literal('bottom')]),
])).max(MAX_ENTRIES);
const persistedPositions = new Map<string, number | 'bottom'>();
let hydrated = false;
let dirty = false;
let saveTimer: ReturnType<typeof setTimeout> | undefined;

function hydratePositions(): void {
  if (hydrated) return;
  hydrated = true;
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw || raw.length > MAX_STORAGE_LENGTH) return;
    const parsed = storedPositionsSchema.safeParse(JSON.parse(raw));
    if (parsed.success) {
      for (const [key, value] of parsed.data) persistedPositions.set(key, value);
    }
  } catch {
    // Disabled storage and corrupt data must not prevent reading.
  }
}

function flushPositions(): void {
  clearTimeout(saveTimer);
  saveTimer = undefined;
  if (!dirty) return;
  dirty = false;
  try {
    if (persistedPositions.size) {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify([...persistedPositions]));
    } else {
      sessionStorage.removeItem(STORAGE_KEY);
    }
  } catch {
    // The in-memory positions remain usable when storage is unavailable.
  }
}

function scheduleSave(): void {
  dirty = true;
  if (saveTimer === undefined) saveTimer = setTimeout(flushPositions, 200);
}

function persistPosition(key: string, value: number): void {
  if (!key || key.length > 512 || !Number.isFinite(value) || value < 0) return;
  hydratePositions();
  persistedPositions.delete(key);
  persistedPositions.set(key, value);
  if (persistedPositions.size > MAX_ENTRIES) {
    const oldest = persistedPositions.keys().next().value;
    if (oldest !== undefined) persistedPositions.delete(oldest);
  }
  scheduleSave();
}

export const scrollMemory = {
  get(key: string): number | 'bottom' | undefined {
    return positions.get(key);
  },
  set(key: string, value: number | 'bottom'): void {
    // Delete-then-set refreshes insertion order, making eviction least-recent.
    positions.delete(key);
    positions.set(key, value);
    if (positions.size > MAX_ENTRIES) {
      const oldest = positions.keys().next().value;
      if (oldest !== undefined) positions.delete(oldest);
    }
  },
  forget(key: string): void {
    positions.delete(key);
    hydratePositions();
    if (persistedPositions.delete(key)) scheduleSave();
  },
  clear(): void {
    positions.clear();
    persistedPositions.clear();
    hydrated = false;
    dirty = true;
    flushPositions();
  },
};

// Thread/route keys are per-account state — wipe on sign-out/account switch.
registerAuthReset(() => scrollMemory.clear());

// Restore retries: content below the fold often lands a few frames after the
// route swap (lazy pages, query cache hydration). ~10 frames covers that
// without fighting a user who has started scrolling (wheel/touch cancels).
const RESTORE_RETRY_FRAMES = 10;

/**
 * Keyed scroll persistence for a container the caller owns. Saves scrollTop
 * per key while the user scrolls; on key change restores the saved offset
 * (0 for never-visited keys, so positions don't bleed between routes sharing
 * the container).
 */
export function useScrollMemory(
  ref: React.RefObject<HTMLElement | null>,
  key: string,
  { persist = false, ready = true }: { persist?: boolean; ready?: boolean } = {},
): void {
  const restoring = useRef(false);
  // Restore before paint so the incoming route never flashes at the stale offset.
  useLayoutEffect(() => {
    restoring.current = false;
    const el = ref.current;
    if (!el) return;
    if (!ready) {
      el.scrollTop = 0;
      return;
    }
    if (persist) hydratePositions();
    const saved = scrollMemory.get(key) ?? (persist ? persistedPositions.get(key) : undefined);
    const target = typeof saved === 'number' ? saved : 0;
    restoring.current = persist && target > 0;
    el.scrollTop = target;
    if (target === 0) return;

    let cancelled = false;
    let attempts = 0;
    let observer: ResizeObserver | undefined;
    const restore = () => {
      if (cancelled) return;
      el.scrollTop = target;
      if (el.scrollTop >= target - 4) {
        restoring.current = false;
        observer?.disconnect();
      }
    };
    restore();
    // Cold images and async Markdown can expand well after the first frames.
    // Observe the body, not just its fixed-height scrolling viewport.
    if (persist && restoring.current) {
      observer = new ResizeObserver(restore);
      observer.observe(el);
      for (const child of el.children) observer.observe(child);
    }
    const onLoad = () => {
      if (restoring.current) restore();
    };
    if (persist) el.addEventListener('load', onLoad, true);
    const retry = () => {
      if (cancelled) return;
      if (el.scrollTop >= target - 4) return; // reached (content tall enough)
      restore();
      if (++attempts < RESTORE_RETRY_FRAMES) requestAnimationFrame(retry);
    };
    requestAnimationFrame(retry);
    const cancel = () => {
      cancelled = true;
      restoring.current = false;
      observer?.disconnect();
      if (persist) {
        scrollMemory.set(key, el.scrollTop);
        persistPosition(key, el.scrollTop);
      }
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (['ArrowUp', 'ArrowDown', 'PageUp', 'PageDown', 'Home', 'End', ' '].includes(event.key)) cancel();
    };
    el.addEventListener('wheel', cancel, { passive: true });
    el.addEventListener('touchstart', cancel, { passive: true });
    if (persist) {
      el.addEventListener('pointerdown', cancel, { passive: true });
      el.addEventListener('keydown', onKeyDown);
    }
    return () => {
      cancelled = true;
      restoring.current = false;
      observer?.disconnect();
      el.removeEventListener('wheel', cancel);
      el.removeEventListener('touchstart', cancel);
      el.removeEventListener('load', onLoad, true);
      el.removeEventListener('pointerdown', cancel);
      el.removeEventListener('keydown', onKeyDown);
    };
  }, [ref, key, persist, ready]);

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el || !ready) return;
    const onScroll = () => {
      if (restoring.current) return;
      scrollMemory.set(key, el.scrollTop);
      if (persist) persistPosition(key, el.scrollTop);
    };
    el.addEventListener('scroll', onScroll, { passive: true });
    if (persist) window.addEventListener('pagehide', flushPositions);
    return () => {
      el.removeEventListener('scroll', onScroll);
      if (persist) {
        window.removeEventListener('pagehide', flushPositions);
        flushPositions();
      }
    };
  }, [ref, key, persist, ready]);
}
