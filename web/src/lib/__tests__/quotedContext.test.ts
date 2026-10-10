import { describe, expect, it } from 'vitest';
import { formatQuotedContextBlocks, type QuotedContext } from '../quotedContext';

describe('formatQuotedContextBlocks', () => {
  it('keeps multiline selections and chooses a fence longer than embedded backticks', () => {
    const contexts: QuotedContext[] = [{
      text: '第一行\n```js\nconst value = 1;\n```\n最后一行',
      label: '讲义选段 · 5 行',
      source: 'lesson',
    }];
    const formatted = formatQuotedContextBlocks(contexts);
    expect(formatted).toContain('<summary>[讲义选段 · 5 行]</summary>');
    expect(formatted).toContain('````');
    expect(formatted).toContain('```js');
    expect(formatted.endsWith('</details>')).toBe(true);
  });

  it('serializes multiple selections in order', () => {
    const formatted = formatQuotedContextBlocks([
      { text: 'first', label: '讲义选段 · 1 行', source: 'lesson' },
      { text: 'second', label: '回答选段 · 1 行', source: 'answer' },
    ]);
    expect(formatted.indexOf('first')).toBeLessThan(formatted.indexOf('second'));
    expect(formatted).toContain('[回答选段 · 1 行]');
  });
});
