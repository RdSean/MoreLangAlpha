import { describe, expect, it } from 'vitest';

describe('test storage environment', () => {
  it('provides an isolated localStorage implementation', () => {
    localStorage.clear();
    localStorage.setItem('workspace', 'active');

    expect(localStorage.getItem('workspace')).toBe('active');

    localStorage.removeItem('workspace');
    expect(localStorage.getItem('workspace')).toBeNull();
  });
});
