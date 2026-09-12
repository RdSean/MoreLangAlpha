import { describe, expect, it } from 'vitest';
import {
  INLINE_ARTIFACT_MAP,
  INLINE_ARTIFACT_TOOLS,
} from '../InlineArtifactCards';

/**
 * This mapping is pure string convention: a tool name plus an artifact `type`.
 * Nothing else connects a tool that returns an artifact to the component that
 * renders it, so a rename on either side shows up as a blank block in the
 * transcript rather than as a failure. These assertions are the cheap half of
 * the fix; the registry that would make it structural is gap 1 in the design
 * doc's list.
 */
describe('inline artifact registry', () => {
  it('renders a card for every artifact type it accepts', () => {
    for (const artifactType of Object.keys(INLINE_ARTIFACT_MAP)) {
      expect(
        INLINE_ARTIFACT_MAP[artifactType],
        `${artifactType} has no component`,
      ).toBeDefined();
    }
  });

  it('knows the homework tool', () => {
    expect(INLINE_ARTIFACT_TOOLS.has('get_homework_schedule')).toBe(true);
  });

  it('maps the homework artifact discriminator to its card', () => {
    // The artifact's `type` literal is what the render path looks up, so this
    // string has to match `HomeworkScheduleArtifact.type` on the backend. The
    // contract test in src/contracts covers the payload half; this covers the
    // dispatch half.
    expect(INLINE_ARTIFACT_MAP.homework_schedule).toBeDefined();
  });

  it('keeps the existing entries', () => {
    expect(INLINE_ARTIFACT_MAP.automations).toBeDefined();
    expect(INLINE_ARTIFACT_MAP.preview_url).toBeDefined();
    expect(INLINE_ARTIFACT_TOOLS.has('check_automations')).toBe(true);
    expect(INLINE_ARTIFACT_TOOLS.has('GetPreviewUrl')).toBe(true);
  });
});
