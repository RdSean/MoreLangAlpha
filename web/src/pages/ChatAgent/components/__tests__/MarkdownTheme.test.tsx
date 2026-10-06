import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import Markdown from '../Markdown';

describe('Markdown semantic colors', () => {
  it.each(['chat', 'panel', 'compact'] as const)('uses separate theme tokens in %s', (variant) => {
    const { container } = render(<Markdown variant={variant} content={'# One\n\n## Two\n\n### Three\n\n#### Four\n\n**Strong**\n\n> Quote'} />);
    for (const [tag, token] of [['h1', '--color-markdown-h1'], ['h2', '--color-markdown-h2'], ['h3', '--color-markdown-h3'], ['h4', '--color-markdown-h4']]) {
      expect(container.querySelector(tag)?.getAttribute('style')).toContain(`var(${token})`);
    }
    expect(container.querySelector('strong')?.getAttribute('style')).toContain('var(--color-markdown-strong)');
    expect(container.querySelector('blockquote')?.getAttribute('style')).toContain('var(--color-markdown-quote-border)');
  });
});
