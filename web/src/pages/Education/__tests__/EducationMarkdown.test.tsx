import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import EducationMarkdown from '../components/EducationMarkdown';

describe('EducationMarkdown', () => {
  it('keeps actual Markdown quotes and source paragraphs distinct without a target highlight', () => {
    const { container } = render(<EducationMarkdown
      content={'### BEFORE YOU READ\n\nOrdinary exercise text.\n\n> An actual quotation.'}
      sourceLineOffset={283} />);
    expect(container.querySelectorAll('blockquote')).toHaveLength(1);
    expect(container.querySelector('blockquote')).toHaveTextContent('An actual quotation.');
    expect(container.querySelector('[data-source-highlight]')).toBeNull();
    expect(screen.getByText('Ordinary exercise text.')).toHaveAttribute('data-source-start-line', '286');
  });

  it('renders saved numeric fraction markup without changing source-line anchors', () => {
    const { container } = render(
      <EducationMarkdown content={'# Fractions\n\n$1/2 = 2/4$'} sourceLineOffset={9} />,
    );
    expect(container.querySelectorAll('.katex')).toHaveLength(1);
    expect(container.querySelector('.katex-error')).toBeNull();
    expect(container.querySelector('annotation')).toHaveTextContent('1/2 = 2/4');
    expect(container.querySelector('[data-source-start-line="12"]')).not.toBeNull();
  });

  it('maps rendered blocks to absolute source lines without decorative range highlights', () => {
    render(
      <EducationMarkdown
        content={'# Opening\n\nFirst paragraph.\n\nSecond paragraph.'}
        sourceLineOffset={9}
      />,
    );

    expect(screen.getByRole('heading', { name: 'Opening' })).toHaveAttribute(
      'data-source-start-line',
      '10',
    );
    expect(screen.getByText('First paragraph.')).toHaveAttribute('data-source-start-line', '12');
    expect(screen.getByText('First paragraph.')).not.toHaveAttribute('data-source-highlight');
    expect(screen.getByText('Second paragraph.')).not.toHaveAttribute('data-source-highlight');
  });
});
