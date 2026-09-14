import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import type { ReactElement } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { CollectionAttentionCard } from '@/components/CollectionAttentionCard';

vi.mock('@/api/resources', () => ({
  listCollectionRisk: vi.fn(),
}));

import { listCollectionRisk } from '@/api/resources';

function wrap(ui: ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('CollectionAttentionCard — QOS-0038', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders nothing when no customer is overdue past 30 days', async () => {
    vi.mocked(listCollectionRisk).mockResolvedValue([
      {
        customerId: 1,
        customerName: 'Fresh Customer',
        outstanding: '500',
        overdueAmount: '0',
        status: 'open',
        ageing: { current: '500', '1_30': '0', '31_60': '0', '61_90': '0', '90_plus': '0' },
      },
    ]);
    const { container } = wrap(<CollectionAttentionCard />);
    await waitFor(() => expect(listCollectionRisk).toHaveBeenCalled());
    expect(container.textContent).toBe('');
  });

  it('surfaces a count + total for customers overdue past 30 days, linking to their ledger', async () => {
    vi.mocked(listCollectionRisk).mockResolvedValue([
      {
        customerId: 7,
        customerName: 'Overdue Trader',
        outstanding: '9000',
        overdueAmount: '9000',
        status: 'overdue',
        ageing: { current: '0', '1_30': '0', '31_60': '9000', '61_90': '0', '90_plus': '0' },
      },
      {
        customerId: 8,
        customerName: 'Within 30 Days',
        outstanding: '200',
        overdueAmount: '200',
        status: 'overdue',
        ageing: { current: '0', '1_30': '200', '31_60': '0', '61_90': '0', '90_plus': '0' },
      },
    ]);
    wrap(<CollectionAttentionCard />);
    await screen.findByText('Customers falling behind');
    // Only the 31-60+ bucket customer counts — the 1-30 one is excluded.
    expect(screen.getByText(/1 customers overdue/)).toBeTruthy();
    const link = screen.getByText('Overdue Trader').closest('a');
    expect(link).toHaveAttribute('href', '/reports/customer-ledger?customer=7');
    expect(screen.queryByText('Within 30 Days')).toBeNull();
  });

  it('shows a credit-hold chip when collection_status is severe', async () => {
    vi.mocked(listCollectionRisk).mockResolvedValue([
      {
        customerId: 9,
        customerName: 'Held Trader',
        outstanding: '12000',
        overdueAmount: '12000',
        status: 'overdue_severe',
        ageing: { current: '0', '1_30': '0', '31_60': '0', '61_90': '0', '90_plus': '12000' },
      },
    ]);
    wrap(<CollectionAttentionCard />);
    await screen.findByText('Held Trader');
    expect(screen.getByText('Credit hold')).toBeTruthy();
  });
});
