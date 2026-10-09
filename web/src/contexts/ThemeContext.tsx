import React, { createContext, useContext, useState, useEffect, useLayoutEffect, useMemo } from 'react';
import { applyAccentHue, getAccentHue } from '@/lib/accentColor';

export type ThemePreference = 'quiet' | 'nasa';
export type ResolvedTheme = ThemePreference;

export interface ThemeContextValue {
  theme: ResolvedTheme;
  preference: ThemePreference;
  setTheme: (value: ThemePreference) => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

function getInitialPreference(): ThemePreference {
  const stored = localStorage.getItem('theme');
  return stored === 'nasa' ? 'nasa' : 'quiet';
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [preference, setPreference] = useState<ThemePreference>(getInitialPreference);
  useLayoutEffect(() => { applyAccentHue(getAccentHue()); }, []);
  useEffect(() => {
    const sync = (event: StorageEvent) => {
      if (event.key === 'accentHue' || event.key === null) applyAccentHue(getAccentHue());
    };
    window.addEventListener('storage', sync);
    return () => window.removeEventListener('storage', sync);
  }, []);

  const theme: ResolvedTheme = preference;

  // Layout phase, not passive: effects run child-before-parent, so a passive
  // stamp here lands AFTER every descendant's effect. Canvas painters that
  // resolve tokens off the stamped `data-theme` (lib/themeTokens) would read
  // the previous theme for one frame on every flip.
  useLayoutEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('theme', preference);
    const favicon = document.querySelector('link[rel="icon"]') as HTMLLinkElement | null;
    if (favicon) favicon.href = '/logo-favicon.svg';
  }, [theme, preference]);

  const setTheme = (value: ThemePreference) => setPreference(value);

  const value = useMemo(
    () => ({ theme, preference, setTheme }),
    [theme, preference],
  );

  return (
    <ThemeContext.Provider value={value}>
      {children}
    </ThemeContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error('useTheme must be used within ThemeProvider');
  return ctx;
}
