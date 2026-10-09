import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { CodeBlock } from '../Markdown';
import SyntaxHighlighter from '../SyntaxHighlighter';

vi.mock('@/contexts/ThemeContext', () => ({ useTheme: () => ({ theme: 'quiet' }) }));
beforeAll(async () => {
  await (SyntaxHighlighter as unknown as { preload: () => Promise<void> }).preload();
});
afterEach(() => vi.restoreAllMocks());

describe('shared code block', () => {
  it('bounds overflowing code and retains expansion during streaming', () => {
    vi.spyOn(HTMLElement.prototype, 'scrollHeight', 'get').mockReturnValue(1200);
    const { rerender } = render(<CodeBlock code={'line\n'.repeat(100)} language="text" />);
    const toggle = screen.getByRole('button', { name: '展开代码' });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(toggle);
    rerender(<CodeBlock code={'line\n'.repeat(101)} language="text" />);
    expect(screen.getByRole('button', { name: '收起代码' })).toHaveAttribute('aria-expanded', 'true');
    fireEvent.click(screen.getByRole('button', { name: '收起代码' }));
    expect(screen.getByRole('button', { name: '展开代码' })).toHaveAttribute('aria-expanded', 'false');
  });
  it('shows short code naturally and copies full text', () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } });
    render(<CodeBlock code="const answer = 42;" language="js" />);
    expect(screen.queryByRole('button', { name: '展开代码' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Copy' }));
    expect(writeText).toHaveBeenCalledWith('const answer = 42;');
  });
  it('exports full code without screen controls even when overflowing', () => {
    vi.spyOn(HTMLElement.prototype, 'scrollHeight', 'get').mockReturnValue(1200);
    const code = 'line\n'.repeat(100);
    const { container } = render(<CodeBlock code={code} language={null} codeTheme="light" />);
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
    expect(container.textContent).toBe(code);
  });
});
