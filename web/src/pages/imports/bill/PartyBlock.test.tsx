import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import type { BillPartyMatch } from '@/types/domain';
import { PartyBlock } from './PartyBlock';

const match = (over: Partial<BillPartyMatch> = {}): BillPartyMatch => ({
  status: 'none',
  id: null,
  candidates: [],
  extracted: { name: 'Retail Buyer LLP', gstin: '' },
  willCreate: true,
  notes: [],
  ...over,
});

function show(over: Partial<React.ComponentProps<typeof PartyBlock>> = {}) {
  const handlers = { onNameChange: vi.fn(), onGstinChange: vi.fn(), onPickCandidate: vi.fn() };
  const view = render(
    <PartyBlock
      isSales
      hasSelectedParty={false}
      match={match()}
      name="Retail Buyer LLP"
      gstin=""
      {...handlers}
      {...over}
    />,
  );
  return { ...view, ...handlers };
}

describe('PartyBlock', () => {
  it('renders nothing once a party is picked in the selector', () => {
    const { container } = show({ hasSelectedParty: true });
    expect(container).toBeEmptyDOMElement();
  });

  it('names the heading for the direction', () => {
    const { unmount } = show();
    expect(screen.getByText('Customer on the bill')).toBeInTheDocument();
    unmount();
    show({ isSales: false });
    expect(screen.getByText('Supplier on the bill')).toBeInTheDocument();
  });

  it('says a new party will be created when nothing matched', () => {
    show();
    expect(screen.getByText('A new party will be created: Retail Buyer LLP')).toBeInTheDocument();
  });

  it('says who it matched', () => {
    show({
      match: match({
        status: 'matched',
        id: 4,
        willCreate: false,
        candidates: [{ id: 4, name: 'Retail Buyer LLP', gstin: '29AABCU9603R1ZX' }],
      }),
    });
    expect(screen.getByText('Matched to Retail Buyer LLP')).toBeInTheDocument();
    expect(screen.queryByText(/will be created/)).not.toBeInTheDocument();
  });

  it('offers similar parties and lets the reviewer pick one', async () => {
    const h = show({
      match: match({
        status: 'candidates',
        candidates: [
          { id: 7, name: 'Retail Buyers', gstin: '29AABCU9603R1ZX', score: 0.9 },
          { id: 8, name: 'Retail Buyer Co' },
        ],
      }),
    });
    expect(screen.getByText('Similar names found. Pick one, or keep it as new.')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Retail Buyers · 29AABCU9603R1ZX' }));
    expect(h.onPickCandidate).toHaveBeenCalledWith(7);
    // keeping it as new is still on offer
    expect(screen.getByText('A new party will be created: Retail Buyer LLP')).toBeInTheDocument();
  });

  it('asks the reviewer to choose when the GSTIN and the name belong to different parties', async () => {
    const h = show({
      match: match({
        status: 'conflict',
        willCreate: false,
        candidates: [
          { id: 1, name: 'By GSTIN', gstin: '29AABCU9603R1ZX' },
          { id: 2, name: 'By name' },
        ],
      }),
    });
    expect(screen.getByText(/belong to different parties/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'By name' }));
    expect(h.onPickCandidate).toHaveBeenCalledWith(2);
    expect(screen.queryByText(/will be created/)).not.toBeInTheDocument();
  });

  it('shows the reason a party was refused (inactive or blocked)', () => {
    show({
      match: match({
        status: 'inactive_match',
        willCreate: false,
        notes: ['Old Co matches this GSTIN but is blocked — reactivate it or pick another customer.'],
      }),
    });
    expect(screen.getByText(/matches this GSTIN but is blocked/)).toBeInTheDocument();
    expect(screen.queryByText(/will be created/)).not.toBeInTheDocument();
  });

  it('shows warnings such as the walk-in customer note', () => {
    show({ match: match({ notes: ['This looks like the walk-in/cash customer; pick a real customer.'] }) });
    expect(screen.getByText(/walk-in\/cash customer/)).toBeInTheDocument();
  });

  it('passes name edits up and upper-cases the GSTIN', async () => {
    const h = show({ name: '', gstin: '' });
    await userEvent.type(screen.getByLabelText('Name on the bill'), 'A');
    expect(h.onNameChange).toHaveBeenLastCalledWith('A');
    await userEvent.type(screen.getByLabelText('GSTIN on the bill'), 'a');
    expect(h.onGstinChange).toHaveBeenLastCalledWith('A');
  });

  it('limits the GSTIN to 15 characters', () => {
    show();
    expect(screen.getByLabelText('GSTIN on the bill')).toHaveAttribute('maxlength', '15');
  });

  it('shows a message when neither a party nor a name is given', () => {
    show({ name: '', error: 'Choose a party or type the name from the bill.' });
    expect(screen.getByText('Choose a party or type the name from the bill.')).toBeInTheDocument();
  });
});
