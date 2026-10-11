import { describe, expect, it } from 'vitest';
import { getNewChatNavigation } from '../AppSidebar';
import { getVisibleNavItems } from '../../nav/navItems';
import enUS from '../../../locales/en-US.json';
import zhCN from '../../../locales/zh-CN.json';

describe('getNewChatNavigation', () => {
  it('opens a student current Flash workspace directly at a blank thread', () => {
    expect(getNewChatNavigation('student', '11111111-1111-4111-8111-111111111111')).toEqual({
      path: '/chat/t/__default__',
      state: {
        workspaceId: '11111111-1111-4111-8111-111111111111',
        workspaceStatus: 'flash',
        agentMode: 'flash',
      },
    });
  });

  it('keeps the workspace gallery for parents and students without a current workspace', () => {
    expect(getNewChatNavigation('parent', null)).toEqual({ path: '/chat' });
    expect(getNewChatNavigation('student', null)).toEqual({ path: '/chat' });
  });
});

describe('library navigation visibility', () => {
  it('exposes assigned textbooks on both student navigation surfaces', () => {
    for (const includeSettings of [false, true]) {
      expect(getVisibleNavItems('student', { includeSettings }).find(item => item.key === '/education/learn')).toMatchObject({ labelKey: 'sidebar.myTextbooks' });
    }
    expect(getVisibleNavItems('parent').map(item => item.key)).not.toContain('/education/learn');
  });

  it('shows documents in both desktop and mobile navigation for a parent', () => {
    expect(getVisibleNavItems('parent').map((item) => item.key)).toContain('/documents');
    expect(getVisibleNavItems('parent', { includeSettings: true }).map((item) => item.key)).toContain('/documents');
  });

  it('keeps the /documents route while showing the Library label in both locales', () => {
    expect(getVisibleNavItems('parent').find((item) => item.key === '/documents')).toMatchObject({
      key: '/documents',
      labelKey: 'sidebar.documents',
    });
    expect(enUS.sidebar.documents).toBe('Library');
    expect(zhCN.sidebar.documents).toBe('图书馆');
  });

  it('hides documents from both navigation surfaces for a student', () => {
    expect(getVisibleNavItems('student').map((item) => item.key)).not.toContain('/documents');
    expect(getVisibleNavItems('student', { includeSettings: true }).map((item) => item.key)).not.toContain('/documents');
  });

  it('shows textbook processing as a parent-only top-level entry', () => {
    expect(getVisibleNavItems('parent').find((item) => item.key === '/textbooks')).toMatchObject({
      key: '/textbooks',
      labelKey: 'sidebar.textbooks',
    });
    expect(enUS.sidebar.textbooks).toBe('Textbooks');
    expect(zhCN.sidebar.textbooks).toBe('教材学习');
    expect(getVisibleNavItems('student').map((item) => item.key)).not.toContain('/textbooks');
  });
});
