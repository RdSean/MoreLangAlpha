import type { ComponentType } from 'react';
import { InlineAutomationCard } from './InlineAutomationCards';
import InlineHomeworkCard from './InlineHomeworkCard';
import { InlinePreviewCard } from './InlinePreviewCard';

/**
 * The one place an artifact type is wired to the component that renders it.
 *
 * This used to be two hand-written maps — a set of tool names and a
 * type-to-component object — with nothing failing if only one of them was
 * updated. A missed entry was a blank block in the transcript and no error.
 * Both are now derived from this table, so adding a card is one edit.
 *
 * The other half of that gap is enforced in
 * `__tests__/artifactIdCoverage.test.ts`: every `type` the backend can emit
 * (published in `web/src/contracts/artifact-types.json`) must appear here or in
 * `ARTIFACT_TYPES_WITHOUT_INLINE_CARD` with a reason.
 */
export interface ArtifactRenderer {
  /** The artifact's `type` discriminator, matched against the payload. */
  artifactType: string;
  /**
   * Tool names whose result should render inline in the transcript, rather
   * than only in the tool-call detail panel. A tool can be listed without an
   * artifact type of its own; this is what decides *when* the card appears.
   */
  tools: string[];
  component: ComponentType<{
    artifact: Record<string, unknown>;
    onClick?: () => void;
  }>;
}

export const ARTIFACT_RENDERERS: ArtifactRenderer[] = [
  {
    artifactType: 'automations',
    tools: ['check_automations', 'create_automation'],
    component: InlineAutomationCard,
  },
  {
    artifactType: 'preview_url',
    tools: ['GetPreviewUrl'],
    component: InlinePreviewCard,
  },
  {
    artifactType: 'homework_schedule',
    tools: ['get_homework_schedule'],
    component: InlineHomeworkCard,
  },
];

/**
 * Artifact types the backend can emit that deliberately have no transcript
 * card, each with the reason. An entry here is a decision; silence is a bug
 * the coverage test catches.
 */
export const ARTIFACT_TYPES_WITHOUT_INLINE_CARD: Record<string, string> = {
  // Empty today: every published artifact type has a card. Kept as the explicit
  // place to record a deliberate omission.
};

export const INLINE_ARTIFACT_MAP: Record<string, ArtifactRenderer['component']> =
  Object.fromEntries(ARTIFACT_RENDERERS.map((entry) => [entry.artifactType, entry.component]));

export const INLINE_ARTIFACT_TOOLS: Set<string> = new Set(
  ARTIFACT_RENDERERS.flatMap((entry) => entry.tools),
);
