import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ThemeProvider } from '@/contexts/ThemeContext';
import { CodeBlock } from '../Markdown';
import CodeEditor from '../viewers/CodeEditor';

vi.mock('../SyntaxHighlighter', () => ({
  default: ({ style }: { style: { palette: string } }) => <pre data-testid="code" data-palette={style.palette} />,
  oneLight: { palette: 'light' }, oneDark: { palette: 'dark' },
}));
vi.mock('@monaco-editor/react', () => ({
  default: ({ theme }: { theme: string }) => <div data-testid="editor" data-theme={theme} />,
  DiffEditor: ({ theme }: { theme: string }) => <div data-testid="diff" data-theme={theme} />,
}));

describe.each(['quiet', 'nasa'])('%s code surfaces', (theme) => {
  it('uses readable light code and editor palettes', () => {
    localStorage.setItem('theme', theme);
    render(<ThemeProvider><CodeBlock language="js" code="const value = 1;" /><CodeEditor value="const value = 1;" originalValue="" diffMode /></ThemeProvider>);
    expect(screen.getByTestId('code')).toHaveAttribute('data-palette', 'light');
    expect(screen.getByTestId('editor')).toHaveAttribute('data-theme', 'vs');
    expect(screen.getByTestId('diff')).toHaveAttribute('data-theme', 'vs');
  });
});
