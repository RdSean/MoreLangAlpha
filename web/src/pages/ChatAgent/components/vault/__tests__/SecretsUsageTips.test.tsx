import { describe, it, expect } from 'vitest';
import { screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import { renderWithProviders } from '@/test/utils';

import { SecretsUsageTips } from '../SecretsUsageTips';

/**
 * The popover is the only place the "when would I use one" copy exists, so the
 * wiring that matters is that the trigger the header renders actually opens it
 * and that all three scenarios arrive — a renamed key would otherwise ship as
 * a blank panel, which the locale-parity sweep cannot see.
 */
describe('SecretsUsageTips', () => {
  it('keeps the panel closed until the trigger is used', () => {
    renderWithProviders(<SecretsUsageTips />);

    expect(screen.queryByText(/Installing a plugin/i)).not.toBeInTheDocument();
  });

  it('opens with every scenario and both scope notes', () => {
    renderWithProviders(<SecretsUsageTips />);

    fireEvent.click(screen.getByRole('button', { name: /tips/i }));

    expect(screen.getByText(/Installing a plugin/i)).toBeInTheDocument();
    expect(screen.getByText(/Connecting a server or connector/i)).toBeInTheDocument();
    expect(screen.getByText(/While the assistant works/i)).toBeInTheDocument();
    expect(screen.getByText(/Account or workspace\?/i)).toBeInTheDocument();
    expect(screen.getByText(/Good to know/i)).toBeInTheDocument();
  });
});
