import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ProposalBody } from '.';

describe('ComparisonRenderer', () => {
  it('shows the differences, owner-only notes, and the editable message', () => {
    render(
      <ProposalBody
        renderer="comparison"
        disabled={false}
        onChange={vi.fn()}
        value={{
          rows: [{ field: 'Widget: rate', left: '100.00', right: '120.00', mismatch: true }],
          internalNotes: ['No goods receipt is recorded against this bill yet.'],
          text: 'Dear Mega Foods, the rate differs.',
        }}
      />,
    );
    expect(screen.getByText('Widget: rate')).toBeInTheDocument();
    expect(screen.getByText('Differs')).toBeInTheDocument();
    expect(screen.getByText('No goods receipt is recorded against this bill yet.')).toBeInTheDocument();
    expect(screen.getByDisplayValue('Dear Mega Foods, the rate differs.')).toBeInTheDocument();
  });

  it('is table-only when the payload has no message', () => {
    render(<ProposalBody renderer="comparison" disabled onChange={vi.fn()} value={{ rows: [{ field: 'A', left: '1', right: '1' }] }} />);
    expect(screen.queryByRole('textbox')).toBeNull();
  });
});
