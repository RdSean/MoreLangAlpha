import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import i18n from '@/i18n';
import { ThemeColorSettings } from '../components/ThemeColorSettings';

beforeEach(() => {
  localStorage.clear();
  document.documentElement.style.removeProperty('--theme-accent-hue');
  void i18n.changeLanguage('zh-CN');
});

describe('ThemeColorSettings', () => {
  it('applies a preset, restores it on remount, and resets to the system default', () => {
    const view = render(<ThemeColorSettings />);
    fireEvent.click(screen.getByRole('button', { name: '青绿' }));
    expect(document.documentElement.style.getPropertyValue('--theme-accent-hue')).toBe('155');
    view.unmount();
    render(<ThemeColorSettings />);
    expect(screen.getByRole('button', { name: '青绿' })).toHaveAttribute('aria-pressed', 'true');
    fireEvent.click(screen.getByRole('button', { name: '恢复默认' }));
    expect(document.documentElement.style.getPropertyValue('--theme-accent-hue')).toBe('');
    expect(localStorage.getItem('accentHue')).toBeNull();
  });

  it('accepts a custom hue and falls back from corrupt stored preferences', () => {
    localStorage.setItem('accentHue', '999');
    render(<ThemeColorSettings />);
    const slider = screen.getByRole('slider', { name: '自定义色相' });
    expect(slider).toHaveValue('28');
    fireEvent.change(slider, { target: { value: '192' } });
    expect(document.documentElement.style.getPropertyValue('--theme-accent-hue')).toBe('192');
    expect(localStorage.getItem('accentHue')).toBe('192');
  });
});
