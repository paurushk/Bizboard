import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import type { ReactElement, ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { DiscountReportPage } from '@/pages/reports/DiscountReportPage';

const SALES_REPORT = {
  totals: {
    invoice_count: 2,
    discounted_invoice_count: 1,
    line_discount_total: 200,
    header_discount_total: 0,
    total_discount: 200,
    pre_discount_revenue: 2000,
    avg_discount_percent: 10,
  },
  by_party: [{ id: 1, name: 'Ravi Kumar', line_discount: 200, revenue: 2000, invoices: 1 }],
  by_product: [{ product_id: 5, product: 'Widget', line_discount: 200, revenue: 2000 }],
  by_period: [{ period: '2026-09-01', line_discount: 200, revenue: 2000 }],
};

const PURCHASE_REPORT = {
  totals: {
    invoice_count: 1,
    discounted_invoice_count: 1,
    line_discount_total: 50,
    header_discount_total: 0,
    total_discount: 50,
    pre_discount_revenue: 1000,
    avg_discount_percent: 5,
  },
  by_party: [{ id: 9, name: 'Mega Suppliers', line_discount: 50, revenue: 1000, invoices: 1 }],
  by_product: [],
  by_period: [],
};

const getSalesDiscountReport = vi.fn(async () => SALES_REPORT);
const getPurchaseDiscountReport = vi.fn(async () => PURCHASE_REPORT);

vi.mock('@/api/resources', () => ({
  getSalesDiscountReport: (...args: unknown[]) => getSalesDiscountReport(...args),
  getPurchaseDiscountReport: (...args: unknown[]) => getPurchaseDiscountReport(...args),
}));

// jsdom has no real layout engine, so @tanstack/react-virtual's ResizeObserver-based
// sizing never reports a non-zero viewport — render every row unwindowed instead.
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

describe('DiscountReportPage', () => {
  it('shows sales totals and the by-customer breakdown by default', async () => {
    wrap(<DiscountReportPage />);
    expect(await screen.findByText('Ravi Kumar')).toBeInTheDocument();
    const row = screen.getByText('Ravi Kumar').closest('tr');
    expect(within(row as HTMLElement).getByText('1')).toBeInTheDocument();
    expect(getSalesDiscountReport).toHaveBeenCalled();
    expect(getPurchaseDiscountReport).not.toHaveBeenCalled();
  });

  it('switches to the purchase report when the Purchases toggle is clicked', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    wrap(<DiscountReportPage />);
    await screen.findByText('Ravi Kumar');
    await userEvent.click(screen.getByRole('button', { name: /purchases/i }));
    expect(await screen.findByText('Mega Suppliers')).toBeInTheDocument();
    expect(getPurchaseDiscountReport).toHaveBeenCalled();
  });

  it('switches breakdown view to Product', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    wrap(<DiscountReportPage />);
    await screen.findByText('Ravi Kumar');
    await userEvent.click(screen.getByRole('button', { name: /^product$/i }));
    expect(await screen.findByText('Widget')).toBeInTheDocument();
  });
});
