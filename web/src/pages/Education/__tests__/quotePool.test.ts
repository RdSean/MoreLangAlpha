import { afterEach, describe, expect, it, vi } from 'vitest';
import { loadQuotePool } from '../quotePool';

afterEach(() => vi.unstubAllGlobals());

describe('loadQuotePool', () => {
  it('fetches only a manifest and one bounded static pool, without credentials', async () => {
    const quotes = [{ contents: '句子', source: '出处' }];
    const fetch = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ files: ['a'.repeat(16) + '-0.json'] })))
      .mockResolvedValueOnce(new Response(JSON.stringify(quotes)));
    vi.stubGlobal('fetch', fetch);
    const signal = new AbortController().signal;
    expect(await loadQuotePool(signal)).toEqual(quotes);
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(fetch.mock.calls[0][1]).toEqual({ signal, cache: 'no-cache', credentials: 'omit' });
    expect(fetch.mock.calls[1][0]).toMatch(/education-quotes\/a{16}-0\.json$/);
    expect(fetch.mock.calls[1][1]).toEqual({ signal, credentials: 'omit' });
  });

  it('rejects a failed manifest and never retries or loads a shard', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response('', { status: 503 }));
    vi.stubGlobal('fetch', fetch);
    await expect(loadQuotePool(new AbortController().signal)).rejects.toThrow('manifest unavailable');
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it('rejects path traversal in the static manifest', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ files: ['../private.json'] })));
    vi.stubGlobal('fetch', fetch);
    await expect(loadQuotePool(new AbortController().signal)).rejects.toThrow('pool unavailable');
    expect(fetch).toHaveBeenCalledTimes(1);
  });
});
