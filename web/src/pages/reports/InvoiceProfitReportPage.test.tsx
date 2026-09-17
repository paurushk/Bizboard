import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import type { ReactElement, ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { InvoiceProfitReportPage } from '@/pages/reports/InvoiceProfitReportPage';

const REPORT = {
  rows: [
    {
      id: 1,
      invoice_id: 101,
      invoice_number: 'INV-0001',
      invoice_date: '2026-09-01',
      invoice_status: 'COMPLETED',
      customer: 'Ravi Kumar',
      revenue_pre_discount: 2000,
      line_discount_total: 0,
      invoice_discount: 0,
      cogs_total: 1600,
      gross_margin: 400,
      margin_percent: 20,
      cost_basis: 'FIFO',
      is_backfilled: false,
    },
    {
      id: 2,
      invoice_id: 102,
      invoice_number: 'INV-0002',
      invoice_date: '2026-09-02',
      invoice_status: 'COMPLETED',
      customer: 'Meena Traders',
      revenue_pre_discount: 500,
      line_discount_total: 0,
      invoice_discount: 0,
      cogs_total: 500,
      gross_margin: 0,
      margin_percent: 0,
      cost_basis: 'PURCHASE_PRICE_FALLBACK',
      is_backfilled: true,
    },
  ],
  totals: {},
};

const getInvoiceProfitReport = vi.fn(async () => REPORT);

vi.mock('@/api/resources', () => ({
  getInvoiceProfitReport: (...args: unknown[]) => getInvoiceProfitReport(...args),
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

describe('InvoiceProfitReportPage', () => {
  it('lists invoice rows with a cost-basis chip', async () => {
    wrap(<InvoiceProfitReportPage />);
    expect(await screen.findByText('INV-0001')).toBeInTheDocument();
    const row = screen.getByText('INV-0001').closest('tr');
    expect(within(row as HTMLElement).getByText('FIFO')).toBeInTheDocument();
  });

  it('flags a purchase-price-fallback margin distinctly from a FIFO one', async () => {
    wrap(<InvoiceProfitReportPage />);
    await screen.findByText('INV-0001');
    const fallbackRow = screen.getByText('INV-0002').closest('tr');
    expect(within(fallbackRow as HTMLElement).getByText('PURCHASE PRICE FALLBACK')).toBeInTheDocument();
  });

  it('links to the breakdown/rollup page', async () => {
    wrap(<InvoiceProfitReportPage />);
    await screen.findByText('INV-0001');
    const link = screen.getByRole('link', { name: /breakdown/i });
    expect(link).toHaveAttribute('href', '/reports/invoice-profit/rollup');
  });
});
