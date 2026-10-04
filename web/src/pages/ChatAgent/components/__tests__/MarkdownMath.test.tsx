import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import Markdown from '../Markdown';
import { ThemeProvider } from '@/contexts/ThemeContext';

describe('Markdown math and currency', () => {
  it.each(['chat', 'panel', 'compact'] as const)(
    'renders numeric inline formulas in the %s variant',
    (variant) => {
      const { container } = render(
        <Markdown variant={variant} content={'$1/2$、$2/4$、$3/6$ and $a/b$'} />,
      );
      expect(container.querySelectorAll('.katex')).toHaveLength(4);
      expect(container.querySelector('.katex-error')).toBeNull();
      expect(Array.from(container.querySelectorAll('annotation')).map((node) => node.textContent))
        .toEqual(['1/2', '2/4', '3/6', 'a/b']);
    },
  );

  it('keeps signed currency amounts as prose alongside formulas', () => {
    const { container } = render(
      <Markdown content={'Cost: $100, $200.50, $-30 and $+4; ratio $1/2$; total \\$334.50.'} />,
    );
    expect(container.querySelectorAll('.katex')).toHaveLength(1);
    expect(container.textContent).toContain('Cost: $100, $200.50, $-30 and $+4; ratio');
    expect(container.textContent).toContain('total $334.50.');
    expect(container.querySelector('.katex-error')).toBeNull();
  });

  it('preserves display formulas, numeric constants and native LaTeX delimiters', () => {
    const { container } = render(
      <Markdown content={'$0$ and $-1/2$\n\n$$\n1 + 2 = 3\n$$\n\n\\(1/2\\)\n\n\\[\n\\frac{2}{4} = \\frac{1}{2}\n\\]'} />,
    );
    expect(container.querySelectorAll('.katex')).toHaveLength(5);
    expect(container.querySelectorAll('.katex-display')).toHaveLength(2);
    expect(container.querySelector('.katex-error')).toBeNull();
  });

  it('preserves amounts in links and does not turn currency before algebra into math', () => {
    const { container } = render(
      <Markdown content={'Pay $100 and solve $x+1$; [price](https://example.com/?price=$100).'} />,
    );
    expect(container.querySelectorAll('.katex')).toHaveLength(1);
    expect(container.textContent).toContain('Pay $100 and solve');
    expect(screen.getByRole('link', { name: 'price' })).toHaveAttribute('href', 'https://example.com/?price=$100');
  });

  it.each(['($x+1$)', '**$x+1$**', '[$x+1$](https://example.com)'])(
    'keeps currency separate from a formula inside %s',
    (formula) => {
      const { container } = render(<Markdown content={`Pay $100 ${formula}.`} />);
      expect(container.textContent).toContain('Pay $100 ');
      expect(container.querySelectorAll('.katex')).toHaveLength(1);
      expect(container.querySelector('annotation')).toHaveTextContent('x+1');
    },
  );

  it('does not pair currency with a dollar inside a later link destination', () => {
    const { container } = render(
      <Markdown content={'Return $100; see [docs](https://example.com/$docs).'} />,
    );
    expect(container.querySelector('.katex')).toBeNull();
    expect(container.textContent).toContain('Return $100; see');
    expect(screen.getByRole('link', { name: 'docs' })).toHaveAttribute('href', 'https://example.com/$docs');
  });

  it('preserves stars in superscripts including repeated stars inside TeX groups', () => {
    const { container } = render(<Markdown content={'$2^*$ and $2^{**}$'} />);
    expect(container.querySelectorAll('.katex')).toHaveLength(2);
    expect(Array.from(container.querySelectorAll('annotation')).map((node) => node.textContent))
      .toEqual(['2^*', '2^{**}']);
  });

  it('does not consume a formula opening dollar across Markdown emphasis', () => {
    const { container } = render(<Markdown content={'Pay $100 **x=$x+1$**.'} />);
    expect(container.textContent).toContain('Pay $100 ');
    expect(container.querySelectorAll('.katex')).toHaveLength(1);
    expect(container.querySelector('annotation')).toHaveTextContent('x+1');
  });

  it('does not rewrite dollars or LaTeX inside code', () => {
    render(<ThemeProvider><Markdown content={'`$1/2$ \\(x\\) $100`\n\n```text\n$1/2$ \\[x\\] $100\n```'} codeTheme="light" /></ThemeProvider>);
    expect(screen.getByText('$1/2$ \\(x\\) $100')).toBeInTheDocument();
    expect(screen.getByText('$1/2$ \\[x\\] $100')).toBeInTheDocument();
  });
});
