import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import type { ReactElement, ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { DiscountReportPage } from '@/pages/reports/DiscountReportPage';

const SALES_REPORT = {
  totals: {
    invoiceCount: 2,
    discountedInvoiceCount: 1,
    lineDiscountTotal: 200,
    headerDiscountTotal: 0,
    totalDiscount: 200,
    preDiscountRevenue: 2000,
    avgDiscountPercent: 10,
  },
  byParty: [{ id: 1, name: 'Ravi Kumar', lineDiscount: 200, revenue: 2000, invoices: 1 }],
  byProduct: [{ productId: 5, product: 'Widget', lineDiscount: 200, revenue: 2000 }],
  byPeriod: [{ period: '2026-09-01', lineDiscount: 200, revenue: 2000 }],
};

const PURCHASE_REPORT = {
  totals: {
    invoiceCount: 1,
    discountedInvoiceCount: 1,
    lineDiscountTotal: 50,
    headerDiscountTotal: 0,
    totalDiscount: 50,
    preDiscountRevenue: 1000,
    avgDiscountPercent: 5,
  },
  byParty: [{ id: 9, name: 'Mega Suppliers', lineDiscount: 50, revenue: 1000, invoices: 1 }],
  byProduct: [],
  byPeriod: [],
};

const getSalesDiscountReport = vi.fn(async (_params?: Record<string, string>) => SALES_REPORT);
const getPurchaseDiscountReport = vi.fn(async (_params?: Record<string, string>) => PURCHASE_REPORT);

vi.mock('@/api/resources', () => ({
  getSalesDiscountReport: (...args: unknown[]) =>
    getSalesDiscountReport(...(args as [Record<string, string>?])),
  getPurchaseDiscountReport: (...args: unknown[]) =>
    getPurchaseDiscountReport(...(args as [Record<string, string>?])),
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
