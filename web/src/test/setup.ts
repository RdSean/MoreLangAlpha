/// <reference types="vitest/globals" />
import '@testing-library/jest-dom';
// Side-effect import: initializes i18next with the same en-US/zh-CN
// resources the app uses, so `t()` in components returns real strings
// instead of bare key paths under test.
import '@/i18n';

class TestStorage implements Storage {
  private readonly entries = new Map<string, string>();

  get length() {
    return this.entries.size;
  }

  clear() {
    this.entries.clear();
  }

  getItem(key: string) {
    return this.entries.get(String(key)) ?? null;
  }

  key(index: number) {
    return Array.from(this.entries.keys())[index] ?? null;
  }

  removeItem(key: string) {
    this.entries.delete(String(key));
  }

  setItem(key: string, value: string) {
    this.entries.set(String(key), String(value));
  }
}

// Node 25 exposes an undefined localStorage when no --localstorage-file is
// configured. Give each Vitest worker an in-memory browser-compatible store.
const testLocalStorage = new TestStorage();
Object.defineProperty(globalThis, 'localStorage', {
  configurable: true,
  value: testLocalStorage,
});
Object.defineProperty(window, 'localStorage', {
  configurable: true,
  value: testLocalStorage,
});

// Mock window.matchMedia for framer-motion
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }),
});

// Mock IntersectionObserver
class IntersectionObserverMock {
  observe = vi.fn();
  unobserve = vi.fn();
  disconnect = vi.fn();
}
window.IntersectionObserver = IntersectionObserverMock as unknown as typeof IntersectionObserver;

// Mock ResizeObserver
class ResizeObserverMock {
  observe = vi.fn();
  unobserve = vi.fn();
  disconnect = vi.fn();
}
window.ResizeObserver = ResizeObserverMock as unknown as typeof ResizeObserver;
