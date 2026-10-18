import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import type { Lead } from '@/api/crm';
import { DedupeReviewDialog } from '@/pages/crm/DedupeReviewDialog';

const { getDedupeCandidates, resolveDedupe } = vi.hoisted(() => ({
  getDedupeCandidates: vi.fn(),
  resolveDedupe: vi.fn(),
}));

vi.mock('@/api/crm', () => ({
  getDedupeCandidates: (...a: unknown[]) => getDedupeCandidates(...a),
  resolveDedupe: (...a: unknown[]) => resolveDedupe(...a),
}));

const lead = { id: 7, name: 'Asha Traders', phone: '9876543210', email: 'a@x.test' } as Lead;

function setup() {
  const onClose = vi.fn();
  const onResolved = vi.fn();
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <DedupeReviewDialog lead={lead} onClose={onClose} onResolved={onResolved} />
    </QueryClientProvider>,
  );
  return { onClose, onResolved };
}

describe('DedupeReviewDialog', () => {
  it('shows candidates and resolves as the same customer', async () => {
    getDedupeCandidates.mockResolvedValue({
      customers: [{ id: 5, name: 'Asha Stores', phone: '9876543210', email: '', gstin: '' }],
      leads: [],
    });
    resolveDedupe.mockResolvedValue({});
    const { onResolved } = setup();
    expect(await screen.findByText('Asha Stores')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Same customer' }));
    await waitFor(() => expect(resolveDedupe).toHaveBeenCalledWith(7, { decision: 'same_customer', customer_id: 5 }));
    await waitFor(() => expect(onResolved).toHaveBeenCalled());
  });

  it('lets the user say the lead is different', async () => {
    getDedupeCandidates.mockResolvedValue({ customers: [], leads: [] });
    resolveDedupe.mockResolvedValue({});
    setup();
    await userEvent.click(await screen.findByRole('button', { name: /different/i }));
    await waitFor(() => expect(resolveDedupe).toHaveBeenCalledWith(7, { decision: 'different' }));
  });

  it('shows the server error and does not close when resolving fails', async () => {
    getDedupeCandidates.mockResolvedValue({ customers: [], leads: [] });
    resolveDedupe.mockRejectedValue(new Error('boom'));
    const { onResolved } = setup();
    await userEvent.click(await screen.findByRole('button', { name: /different/i }));
    await waitFor(() => expect(resolveDedupe).toHaveBeenCalled());
    expect(onResolved).not.toHaveBeenCalled();
  });
});
