import { describe, expect, it } from 'vitest';
import { api } from '../client';

describe('api axios instance', () => {
  it('uses browser credentials for local HttpOnly session cookies', () => {
    expect(api.defaults.withCredentials).toBe(true);
  });

  it('keeps JSON as the default content type', () => {
    expect(api.defaults.headers.common?.['Content-Type'] || api.defaults.headers['Content-Type']).toBe('application/json');
  });
});
