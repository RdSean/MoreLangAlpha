import { describe, expect, it } from 'vitest';
import { getNewChatNavigation } from '../AppSidebar';
import { getVisibleNavItems } from '../../nav/navItems';

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

describe('knowledge library navigation visibility', () => {
  it('shows documents in both desktop and mobile navigation for a parent', () => {
    expect(getVisibleNavItems('parent').map((item) => item.key)).toContain('/documents');
    expect(getVisibleNavItems('parent', { includeSettings: true }).map((item) => item.key)).toContain('/documents');
  });

  it('hides documents from both navigation surfaces for a student', () => {
    expect(getVisibleNavItems('student').map((item) => item.key)).not.toContain('/documents');
    expect(getVisibleNavItems('student', { includeSettings: true }).map((item) => item.key)).not.toContain('/documents');
  });
});
