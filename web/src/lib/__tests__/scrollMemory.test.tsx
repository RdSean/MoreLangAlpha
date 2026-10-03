import { useRef } from 'react';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { runAuthResets } from '@/lib/authResets';
import { scrollMemory, useScrollMemory } from '../scrollMemory';

const STORAGE_KEY = 'langalpha:reader-scroll:v1';

function Reader({ id = 'book:kp:source', persist = true, ready = true }) {
  const ref = useRef<HTMLDivElement>(null);
  useScrollMemory(ref, id, { persist, ready });
  return <div ref={ref} data-testid="reader" />;
}

beforeEach(() => {
  vi.useFakeTimers();
  scrollMemory.clear();
  sessionStorage.clear();
});

afterEach(() => {
  cleanup();
  scrollMemory.clear();
  vi.restoreAllMocks();
  vi.useRealTimers();
});

describe('opt-in reader session scroll memory', () => {
  it('restores persisted position only once the body is ready', () => {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify([['book:kp:source', 580]]));
    const { rerender } = render(<Reader ready={false} />);
    const reader = screen.getByTestId('reader');
    reader.scrollTop = 0;
    fireEvent.scroll(reader);
    act(() => vi.advanceTimersByTime(1000));
    expect(JSON.parse(sessionStorage.getItem(STORAGE_KEY)!)).toEqual([['book:kp:source', 580]]);
    rerender(<Reader />);
    expect(reader.scrollTop).toBe(580);
  });

  it('keeps ordinary containers memory-only', () => {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify([['book:kp:source', 580]]));
    render(<Reader persist={false} />);
    const reader = screen.getByTestId('reader');
    expect(reader.scrollTop).toBe(0);
    reader.scrollTop = 240;
    fireEvent.scroll(reader);
    act(() => vi.advanceTimersByTime(1000));
    expect(scrollMemory.get('book:kp:source')).toBe(240);
    expect(JSON.parse(sessionStorage.getItem(STORAGE_KEY)!)).toEqual([['book:kp:source', 580]]);
  });

  it('coalesces scroll writes and flushes on pagehide before reload', () => {
    render(<Reader />);
    const reader = screen.getByTestId('reader');
    for (const top of [100, 240, 580]) {
      reader.scrollTop = top;
      fireEvent.scroll(reader);
    }
    expect(sessionStorage.getItem(STORAGE_KEY)).toBeNull();
    fireEvent(window, new Event('pagehide'));
    expect(JSON.parse(sessionStorage.getItem(STORAGE_KEY)!)).toEqual([['book:kp:source', 580]]);
  });

  it('writes the latest offset after the bounded cooldown', () => {
    render(<Reader />);
    const reader = screen.getByTestId('reader');
    reader.scrollTop = 240;
    fireEvent.scroll(reader);
    act(() => vi.advanceTimersByTime(250));
    expect(JSON.parse(sessionStorage.getItem(STORAGE_KEY)!)).toEqual([['book:kp:source', 240]]);
  });

  it('clears persisted positions and pending writes on account reset', () => {
    render(<Reader />);
    const reader = screen.getByTestId('reader');
    reader.scrollTop = 240;
    fireEvent.scroll(reader);
    runAuthResets();
    act(() => vi.advanceTimersByTime(1000));
    fireEvent(window, new Event('pagehide'));
    expect(sessionStorage.getItem(STORAGE_KEY)).toBeNull();
    expect(scrollMemory.get('book:kp:source')).toBeUndefined();
  });

  it('forgets persisted keys without deleting other reader positions', () => {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify([['book:kp:source', 580], ['other', 240]]));
    render(<Reader />);
    scrollMemory.forget('book:kp:source');
    fireEvent(window, new Event('pagehide'));
    expect(JSON.parse(sessionStorage.getItem(STORAGE_KEY)!)).toEqual([['other', 240]]);
  });

  it.each(['not json', JSON.stringify([['book:kp:source', -3]]), JSON.stringify([['book:kp:source', '580']]), 'x'.repeat(200_001)])(
    'ignores malformed or oversized stored positions (%#)', (stored) => {
      sessionStorage.setItem(STORAGE_KEY, stored);
      render(<Reader />);
      expect(screen.getByTestId('reader').scrollTop).toBe(0);
    },
  );

  it('still remembers in memory when session storage is blocked', () => {
    vi.spyOn(Object.getPrototypeOf(sessionStorage), 'getItem').mockImplementation(() => { throw new Error('blocked'); });
    vi.spyOn(Object.getPrototypeOf(sessionStorage), 'setItem').mockImplementation(() => { throw new Error('blocked'); });
    const { unmount } = render(<Reader />);
    const reader = screen.getByTestId('reader');
    reader.scrollTop = 240;
    fireEvent.scroll(reader);
    act(() => vi.advanceTimersByTime(1000));
    unmount();
    render(<Reader />);
    expect(screen.getByTestId('reader').scrollTop).toBe(240);
  });

  it('bounds stored reader positions to the latest 300 keys', () => {
    const { rerender } = render(<Reader id="book:0" />);
    for (let index = 0; index < 305; index += 1) {
      rerender(<Reader id={`book:${index}`} />);
      const reader = screen.getByTestId('reader');
      reader.scrollTop = index + 1;
      fireEvent.scroll(reader);
    }
    fireEvent(window, new Event('pagehide'));
    const rows = JSON.parse(sessionStorage.getItem(STORAGE_KEY)!);
    expect(rows).toHaveLength(300);
    expect(rows[0]).toEqual(['book:5', 6]);
    expect(rows.at(-1)).toEqual(['book:304', 305]);
  });

  it('does not save a clamped offset while waiting for cold image layout', () => {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify([['book:kp:source', 580]]));
    const { rerender } = render(<Reader ready={false} />);
    const reader = screen.getByTestId('reader');
    let height = 100;
    let top = 0;
    Object.defineProperty(reader, 'scrollTop', {
      configurable: true, get: () => top, set: (value: number) => { top = Math.min(value, height); },
    });
    rerender(<Reader />);
    expect(top).toBe(100);
    fireEvent.scroll(reader);
    act(() => vi.advanceTimersByTime(1000));
    expect(JSON.parse(sessionStorage.getItem(STORAGE_KEY)!)).toEqual([['book:kp:source', 580]]);
    height = 1000;
    fireEvent.load(reader);
    expect(top).toBe(580);
  });

  it.each(['pointer', 'keyboard', 'wheel'])('stops pending image restoration on user %s input', (input) => {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify([['book:kp:source', 580]]));
    const { rerender } = render(<Reader ready={false} />);
    const reader = screen.getByTestId('reader');
    let height = 100;
    let top = 0;
    Object.defineProperty(reader, 'scrollTop', {
      configurable: true, get: () => top, set: (value: number) => { top = Math.min(value, height); },
    });
    rerender(<Reader />);
    if (input === 'pointer') fireEvent.pointerDown(reader);
    else if (input === 'keyboard') fireEvent.keyDown(reader, { key: 'PageDown' });
    else fireEvent.wheel(reader);
    height = 1000;
    fireEvent.load(reader);
    expect(top).toBe(100);
    fireEvent(window, new Event('pagehide'));
    expect(JSON.parse(sessionStorage.getItem(STORAGE_KEY)!)).toEqual([['book:kp:source', 100]]);
  });
});
