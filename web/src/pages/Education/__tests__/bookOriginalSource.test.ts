import { afterEach, describe, expect, it } from 'vitest';
import { api } from '@/api/client';
import * as education from '../api';

const previous = api.defaults.baseURL;
afterEach(() => { api.defaults.baseURL = previous; });

describe('original PDF source URL', () => {
  it.each([
    ['', '/api/v1/education/textbooks/book%20id/original'],
    ['http://localhost:8000', 'http://localhost:8000/api/v1/education/textbooks/book%20id/original'],
    ['https://example.test/backend/', 'https://example.test/backend/api/v1/education/textbooks/book%20id/original'],
  ])('uses the shared API base %s without fetching PDF bytes', (base, expected) => {
    api.defaults.baseURL = base;
    expect(education.getManagedBookOriginalSource('book id')).toEqual({ url: expected, withCredentials: true });
  });
});
