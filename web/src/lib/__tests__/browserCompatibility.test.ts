import { afterEach, describe, expect, it, vi } from 'vitest';

async function loadCompatibility() {
  vi.resetModules();
  await import('../browserCompatibility');
}

function legacyMedia() {
  const listeners = new Set<(event: MediaQueryListEvent) => void>();
  const media = {
    matches: false,
    media: '(max-width: 767px)',
    addListener: vi.fn((callback: (event: MediaQueryListEvent) => void) => listeners.add(callback)),
    removeListener: vi.fn((callback: (event: MediaQueryListEvent) => void) => listeners.delete(callback)),
  } as unknown as MediaQueryList;
  return { media, fire: () => listeners.forEach(callback => callback({ matches: true } as MediaQueryListEvent)) };
}

afterEach(() => vi.unstubAllGlobals());

describe('browser startup compatibility', () => {
  it('keeps native modern matchMedia untouched', async () => {
    const matchMedia = window.matchMedia;
    await loadCompatibility();
    expect(window.matchMedia).toBe(matchMedia);
  });

  it('delivers legacy changes once per listener and removes subscriptions', async () => {
    const { media, fire } = legacyMedia();
    vi.stubGlobal('matchMedia', vi.fn(() => media));
    await loadCompatibility();
    const query = window.matchMedia(media.media);
    const callback = vi.fn();
    query.addEventListener('change', callback);
    query.addEventListener('change', callback);
    fire();
    expect(callback).toHaveBeenCalledTimes(1);
    expect(callback.mock.contexts[0]).toBe(media);
    query.removeEventListener('change', callback);
    fire();
    expect(callback).toHaveBeenCalledTimes(1);
  });

  it('supports object listeners and once subscriptions', async () => {
    const { media, fire } = legacyMedia();
    vi.stubGlobal('matchMedia', vi.fn(() => media));
    await loadCompatibility();
    const query = window.matchMedia(media.media);
    const listener = { handleEvent: vi.fn() };
    query.addEventListener('change', listener, { once: true });
    fire();
    fire();
    expect(listener.handleEvent).toHaveBeenCalledTimes(1);
    expect(media.removeListener).toHaveBeenCalledTimes(1);
  });
});
