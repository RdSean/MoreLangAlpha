import React from 'react';
import { act, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import { ThemeProvider, useTheme } from '../ThemeContext';

function Consumer() {
  const { theme, preference, setTheme } = useTheme();
  return (
    <div>
      <span data-testid="theme">{theme}</span>
      <span data-testid="preference">{preference}</span>
      <button type="button" onClick={() => setTheme('nasa')}>nasa</button>
    </div>
  );
}

describe('ThemeContext', () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute('data-theme');
  });

  it('defaults to quiet and stamps data-theme=quiet', () => {
    render(<ThemeProvider><Consumer /></ThemeProvider>);

    expect(screen.getByTestId('theme')).toHaveTextContent('quiet');
    expect(screen.getByTestId('preference')).toHaveTextContent('quiet');
    expect(document.documentElement).toHaveAttribute('data-theme', 'quiet');
    expect(localStorage.getItem('theme')).toBe('quiet');
  });

  it('accepts nasa and persists it without a reload', () => {
    render(<ThemeProvider><Consumer /></ThemeProvider>);

    act(() => screen.getByRole('button', { name: 'nasa' }).click());

    expect(screen.getByTestId('theme')).toHaveTextContent('nasa');
    expect(document.documentElement).toHaveAttribute('data-theme', 'nasa');
    expect(localStorage.getItem('theme')).toBe('nasa');
  });

  it.each(['light', 'dark', 'auto', 'unknown'])('maps legacy %s to quiet', (stored) => {
    localStorage.setItem('theme', stored);

    render(<ThemeProvider><Consumer /></ThemeProvider>);

    expect(screen.getByTestId('theme')).toHaveTextContent('quiet');
    expect(localStorage.getItem('theme')).toBe('quiet');
  });
});
