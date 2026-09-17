import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { HelpPageV0 } from './HelpPageV0';

describe('HelpPageV0 FAQ catalog', () => {
  it('shows original conversion FAQ and new sections', () => {
    render(
      <MemoryRouter>
        <HelpPageV0 />
      </MemoryRouter>,
    );
    expect(
      screen.getByText(/How do I set the conversion rate between a base unit and an alternate unit/i),
    ).toBeInTheDocument();
    expect(screen.getByText('Getting started')).toBeInTheDocument();
    expect(screen.getByText('Where is goods received (GRN)?')).toBeInTheDocument();
    expect(screen.getByText('Does Bizboard file GSTR-1 or GSTR-3B on the GST portal?')).toBeInTheDocument();
  });

  it('search matches a new keyword and hides unrelated questions', () => {
    render(
      <MemoryRouter>
        <HelpPageV0 />
      </MemoryRouter>,
    );
    fireEvent.change(screen.getByLabelText(/search faqs/i), { target: { value: 'grn' } });
    expect(screen.getByText('Where is goods received (GRN)?')).toBeInTheDocument();
    expect(
      screen.queryByText(/How do I set the conversion rate between a base unit and an alternate unit/i),
    ).not.toBeInTheDocument();
  });
});
