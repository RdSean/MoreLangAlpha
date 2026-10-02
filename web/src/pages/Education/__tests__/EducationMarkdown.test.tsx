import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import EducationMarkdown from '../components/EducationMarkdown';

describe('EducationMarkdown', () => {
  it('maps rendered blocks to absolute source lines and highlights the target range', () => {
    render(
      <EducationMarkdown
        content={'# Opening\n\nFirst paragraph.\n\nSecond paragraph.'}
        sourceLineOffset={9}
        highlightSourceRange={{ start: 12, end: 12 }}
      />,
    );

    expect(screen.getByRole('heading', { name: 'Opening' })).toHaveAttribute(
      'data-source-start-line',
      '10',
    );
    expect(screen.getByText('First paragraph.')).toHaveAttribute('data-source-start-line', '12');
    expect(screen.getByText('First paragraph.')).toHaveAttribute('data-source-highlight', 'true');
    expect(screen.getByText('Second paragraph.')).not.toHaveAttribute('data-source-highlight');
  });
});
