import { describe, expect, it } from 'vitest';
import { getNewChatNavigation } from '../AppSidebar';

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
