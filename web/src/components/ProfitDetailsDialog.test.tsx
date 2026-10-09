import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ProfitDetailsDialog } from '@/components/ProfitDetailsDialog';

const details = vi.hoisted(() => ({ value: {} as Record<string, unknown> }));

vi.mock('@/api/resources', () => ({
  getInvoiceProfitDetails: async () => details.value,
}));

function renderDialog() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ProfitDetailsDialog invoiceId={7} open onClose={() => undefined} />
    </QueryClientProvider>,
  );
}

const base = {
  lines: [{ name: 'Bolt', quantity: 2, unitName: 'PCS', unitCost: null, lineCost: '0.00', fellBackToPurchasePrice: false, costMissing: true }],
  salesAmount: '236.00',
  totalCost: '0.00',
  taxPayable: '36.00',
  profit: '200.00',
  estimated: true,
  formula: 'Profit = Sales amount − Total cost − GST collected',
};

describe('ProfitDetailsDialog cost warning', () => {
  it('warns when a stocked line has no cost yet, and marks that line', async () => {
    details.value = { ...base, costIncomplete: true };
    renderDialog();
    expect(await screen.findByText(/no purchase cost yet/i)).toBeInTheDocument();
    expect(screen.getByText(/no cost yet/i)).toBeInTheDocument();
  });

  it('shows no warning when every line has a cost', async () => {
    details.value = {
      ...base,
      costIncomplete: false,
      lines: [{ ...base.lines[0], unitCost: '40.00', lineCost: '80.00', costMissing: false }],
    };
    renderDialog();
    expect(await screen.findByText('Bolt')).toBeInTheDocument();
    expect(screen.queryByText(/no purchase cost yet/i)).not.toBeInTheDocument();
  });
});
