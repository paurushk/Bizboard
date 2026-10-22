import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { HelpPageV0 } from './HelpPageV0';

describe('Help page: Business agents', () => {
  const scroll = vi.fn();
  beforeEach(() => {
    scroll.mockClear();
    Element.prototype.scrollIntoView = scroll;
  });
  afterEach(() => {
    // @ts-expect-error jsdom has no scrollIntoView; remove the stub again
    delete Element.prototype.scrollIntoView;
  });

  const open = (hash = '') =>
    render(
      <MemoryRouter initialEntries={[`/help${hash}`]}>
        <HelpPageV0 />
      </MemoryRouter>,
    );

  it('lists the category and its questions', () => {
    open();
    expect(screen.getByText('Business agents')).toBeInTheDocument();
    expect(screen.getByText('What are the business agents, and what can they do?')).toBeInTheDocument();
    expect(screen.getByText('How do I turn a WhatsApp or SMS order into a sales order?')).toBeInTheDocument();
  });

  it('a deep link from the draft panel opens its answer', async () => {
    open('#agents-review-approve');
    const q = screen.getByRole('button', { name: 'How do I review, change and approve a draft?' });
    expect(q.getAttribute('aria-expanded')).toBe('true');
    await waitFor(() => expect(scroll).toHaveBeenCalledTimes(1));
    expect(screen.getByText(/You must save before you can approve/)).toBeInTheDocument();
  });

  it.each([
    ['holdout', 'Why do some customers never get a reminder draft? (the 20% holdout)'],
    ['gstin', 'What other checks does Bill Check make?'],
    ['whatsapp', 'Can an agent change my books, send messages or take money on its own?'],
    ['photo', 'Can the agent read a photo or PDF of an order?'],
  ])('search for "%s" finds its question', (term, question) => {
    open();
    fireEvent.change(screen.getByLabelText(/search faqs/i), { target: { value: term } });
    expect(screen.getByText(question)).toBeInTheDocument();
  });
});
