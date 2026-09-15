import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import artifactFixture from '@/contracts/__tests__/__fixtures__/education-homework.wire.json';
import InlineEducationHomeworkCard from '../InlineEducationHomeworkCard';

/**
 * The fixture is the same real artifact the contract tests use — captured from
 * the service, serialised with `model_dump(mode="json")`, identifiers and the
 * child's name replaced with stable stand-ins. Sharing it is deliberate: the
 * card is being tested against the payload the tool actually produces.
 */
const artifact = artifactFixture as unknown as Record<string, unknown>;

function clone(): Record<string, unknown> {
  return structuredClone(artifact);
}

function renderCard(payload: Record<string, unknown> = artifact, onClick?: () => void) {
  // Deliberately no QueryClientProvider and no router: this component must be a
  // leaf. If it ever grew a data hook, this render would throw.
  return render(<InlineEducationHomeworkCard artifact={payload} onClick={onClick} />);
}

describe('InlineEducationHomeworkCard', () => {
  it('shows what the tool created instead of stopping at the tool step', () => {
    renderCard();

    expect(screen.getByTestId('inline-education-homework-card')).toBeInTheDocument();
    expect(screen.getByTestId('inline-education-homework-title')).toHaveTextContent(
      (artifact.task as { title: string }).title,
    );
    expect(screen.getByTestId('inline-education-homework-student')).toHaveTextContent(
      String(artifact.student_name),
    );
  });

  it('marks a text-only task rather than implying attachments', () => {
    renderCard();
    expect(screen.getByTestId('inline-education-homework-text-only')).toBeInTheDocument();

    const withAttachments = clone();
    withAttachments.attachments_supported = true;
    // Scoped to this render's container: the first card is still mounted, so a
    // document-wide query would find its tag and pass or fail for the wrong
    // reason.
    const { container } = renderCard(withAttachments);
    expect(
      container.querySelector('[data-testid="inline-education-homework-text-only"]'),
    ).toBeNull();
  });

  it('renders a notice instead of throwing on a payload that does not match', () => {
    // A payload the tool cannot produce still reaches the transcript if the
    // contract drifts; the thread must survive it.
    renderCard({ type: 'education_homework', success: true });

    expect(screen.getByTestId('inline-education-homework-invalid')).toBeInTheDocument();
    expect(screen.queryByTestId('inline-education-homework-card')).not.toBeInTheDocument();
  });

  it('hands the click to the caller when one is provided', () => {
    const onClick = vi.fn();
    renderCard(artifact, onClick);

    screen.getByTestId('inline-education-homework-card').click();
    expect(onClick).toHaveBeenCalledTimes(1);
  });
});
