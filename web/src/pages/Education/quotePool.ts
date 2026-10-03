export interface WaitingQuote {
  contents: string;
  source: string;
}

export async function loadQuotePool(signal: AbortSignal): Promise<WaitingQuote[]> {
  const base = `${import.meta.env.BASE_URL}education-quotes/`;
  const manifestResponse = await fetch(`${base}manifest.json`, { signal, cache: 'no-cache', credentials: 'omit' });
  if (!manifestResponse.ok) throw new Error('Quote manifest unavailable');
  const manifest = await manifestResponse.json() as { files: string[] };
  const file = manifest.files[Math.floor(Math.random() * manifest.files.length)];
  if (!file || !/^[a-f0-9]{16}-\d+\.json$/.test(file)) throw new Error('Quote pool unavailable');
  const response = await fetch(`${base}${file}`, { signal, credentials: 'omit' });
  if (!response.ok) throw new Error('Quote pool unavailable');
  const quotes = await response.json() as WaitingQuote[];
  if (!Array.isArray(quotes) || quotes.length === 0 || quotes.length > 250) throw new Error('Quote pool invalid');
  for (let index = quotes.length - 1; index > 0; index -= 1) {
    const other = Math.floor(Math.random() * (index + 1));
    [quotes[index], quotes[other]] = [quotes[other], quotes[index]];
  }
  return quotes;
}
