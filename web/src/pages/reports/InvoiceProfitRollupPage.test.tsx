import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import type { ReactElement, ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { InvoiceProfitRollupPage } from '@/pages/reports/InvoiceProfitRollupPage';

const BY_CUSTOMER = { rows: [{ id: 1, name: 'Ravi Kumar', invoices: 2, revenue: 4000, cogs: 3000, margin: 1000 }] };
const BY_PRODUCT = { rows: [{ id: 5, name: 'Widget', revenue: 4000, cogs: 3000, margin: 1000 }] };

const getInvoiceProfitRollup = vi.fn(async (groupBy: string, _params?: unknown) =>
  groupBy === 'product' ? BY_PRODUCT : BY_CUSTOMER,
);

vi.mock('@/api/resources', () => ({
  getInvoiceProfitRollup: (groupBy: string, params?: unknown) => getInvoiceProfitRollup(groupBy, params),
}));

vi.mock('@/components/VirtualizedTable', () => ({
  VirtualizedTable: ({
    rowCount,
    children,
  }: {
    rowCount?: number;
    children: (args: {
      rows: { index: number; start: number; end: number; size: number }[];
      totalSize: number;
      measureElement: () => void;
    }) => ReactNode;
  }) => {
    const count = rowCount ?? 0;
    const rows = Array.from({ length: count }, (_, index) => ({
      index,
      start: index * 52,
      end: (index + 1) * 52,
      size: 52,
    }));
    return children({ rows, totalSize: count * 52, measureElement: () => {} });
  },
}));

function wrap(ui: ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('InvoiceProfitRollupPage', () => {
  it('defaults to the by-customer breakdown', async () => {
    wrap(<InvoiceProfitRollupPage />);
    expect(await screen.findByText('Ravi Kumar')).toBeInTheDocument();
    expect(getInvoiceProfitRollup).toHaveBeenCalledWith('customer', expect.anything());
  });

  it('switches to the by-product breakdown', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    wrap(<InvoiceProfitRollupPage />);
    await screen.findByText('Ravi Kumar');
    await userEvent.click(screen.getByRole('button', { name: /^product$/i }));
    expect(await screen.findByText('Widget')).toBeInTheDocument();
    expect(getInvoiceProfitRollup).toHaveBeenCalledWith('product', expect.anything());
  });
});
