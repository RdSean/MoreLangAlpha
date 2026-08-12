import { describe, expect, it } from 'vitest';
import {
  classifyAgentPath,
  computeAgentArtifactRouting,
  topicFromMemoryKey,
  workspaceRelativePath,
} from '../agentPaths';

describe('workspaceRelativePath', () => {
  it('normalizes sandbox and file URL paths', () => {
    expect(workspaceRelativePath('/home/workspace/agent.md')).toBe('agent.md');
    expect(workspaceRelativePath('file:///home/daytona/work/notes.md')).toBe('work/notes.md');
  });
});

describe('classifyAgentPath', () => {
  it('classifies user and workspace memory', () => {
    expect(classifyAgentPath('.agents/user/memory/profile.md')).toMatchObject({
      kind: 'memory', tier: 'user', key: 'profile.md',
    });
    expect(classifyAgentPath('.agents/workspace/memory/plan.md')).toMatchObject({
      kind: 'memory', tier: 'workspace', key: 'plan.md',
    });
  });

  it('classifies memo and skill paths', () => {
    expect(classifyAgentPath('.agents/user/memo/brief.md')).toMatchObject({ kind: 'memo', key: 'brief.md' });
    expect(classifyAgentPath('.agents/skills/research/SKILL.md')).toMatchObject({ kind: 'skill', name: 'research' });
  });

  it('keeps arbitrary profile-directory files as regular files', () => {
    expect(classifyAgentPath('.agents/user/profile/preferences.json').kind).toBe('file');
  });
});

describe('computeAgentArtifactRouting', () => {
  it('clears workspace context for user memory and memo entries', () => {
    expect(computeAgentArtifactRouting('.agents/user/memory/profile.md')).toMatchObject({
      targetMemoryKey: 'profile.md', targetMemoryTier: 'user', clearWorkspaceId: true,
    });
    expect(computeAgentArtifactRouting('.agents/user/memo/brief.md')).toMatchObject({
      targetMemoKey: 'brief.md', clearWorkspaceId: true,
    });
  });

  it('uses a cross-workspace reference for workspace memory', () => {
    expect(computeAgentArtifactRouting('__wsref__/ws-1/.agents/workspace/memory/plan.md')).toMatchObject({
      targetMemoryKey: 'plan.md', targetMemoryTier: 'workspace', setWorkspaceId: 'ws-1',
    });
  });
});

describe('topicFromMemoryKey', () => {
  it('creates a readable topic from a memory filename', () => {
    expect(topicFromMemoryKey('family_preferences.md')).toBe('family preferences');
  });
});
