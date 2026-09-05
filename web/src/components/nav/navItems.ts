import { BookOpenCheck, LayoutDashboard, LibraryBig, MessagesSquare, Settings, Timer } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

export interface NavItem {
  /** Route path. */
  key: string;
  icon: LucideIcon;
  /** i18n key resolved via t(). */
  labelKey: string;
  /** Active-state strategy: 'prefix' = pathname.startsWith(key); 'exact-or-sub' = exact match or key + '/' sub-path. */
  match: 'prefix' | 'exact-or-sub';
}

// Single source of truth for primary navigation (rail + mobile tab bar).
export const NAV_ITEMS: NavItem[] = [
  { key: '/dashboard', icon: LayoutDashboard, labelKey: 'sidebar.dashboard', match: 'exact-or-sub' },
  { key: '/chat', icon: MessagesSquare, labelKey: 'sidebar.chatAgent', match: 'prefix' },
  { key: '/documents', icon: LibraryBig, labelKey: 'sidebar.documents', match: 'exact-or-sub' },
  { key: '/automations', icon: Timer, labelKey: 'sidebar.automations', match: 'exact-or-sub' },
  { key: '/education', icon: BookOpenCheck, labelKey: 'sidebar.education', match: 'exact-or-sub' },
];

// Settings only appears in the mobile tab bar (desktop reaches it via AccountMenu).
export const SETTINGS_ITEM: NavItem = {
  key: '/settings',
  icon: Settings,
  labelKey: 'sidebar.settings',
  match: 'exact-or-sub',
};

export function getVisibleNavItems(
  role: 'parent' | 'student' | null | undefined,
  options: { includeSettings?: boolean } = {},
): NavItem[] {
  const items = role === 'student'
    ? NAV_ITEMS.filter((item) => item.key !== '/automations' && item.key !== '/documents')
    : NAV_ITEMS;
  return options.includeSettings && role !== 'student' ? [...items, SETTINGS_ITEM] : items;
}
