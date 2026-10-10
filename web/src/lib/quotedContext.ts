export interface QuotedContext {
  text: string;
  label: string;
  source: 'lesson' | 'answer';
}

function fenceFor(text: string): string {
  const runs = text.match(/`+/g) ?? [];
  const longest = runs.reduce((length, run) => Math.max(length, run.length), 0);
  return '`'.repeat(Math.max(3, longest + 1));
}

/** Shared wire format for Flash snippets and textbook selections. */
export function formatContextBlock(summary: string, text: string): string {
  const fence = fenceFor(text);
  const safeSummary = summary.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/[\r\n]/g, ' ');
  return `\n<details>\n<summary>${safeSummary}</summary>\n\n${fence}\n${text}\n${fence}\n</details>`;
}

export function formatQuotedContextBlocks(contexts: readonly QuotedContext[]): string {
  return contexts.map(({ text, label }) => formatContextBlock(`[${label}]`, text)).join('\n');
}
