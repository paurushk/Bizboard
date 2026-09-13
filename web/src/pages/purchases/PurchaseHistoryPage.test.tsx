import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import type { ReactElement, ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { PurchaseHistoryPage } from '@/pages/purchases/PurchaseHistoryPage';
import type { PurchaseInvoice } from '@/types/domain';

// G-17 parity check: unlike SalesHistoryPage, this list renders `status`
// directly with no payment-state overlay — pin that a RETURNED purchase
// stays visibly RETURNED, so a future "paid-aware" wrapper added here
// doesn't silently reintroduce the same masking bug on the purchase side.
const ROWS: PurchaseInvoice[] = [
  {
    id: 1,
    number: 'PUR-0001',
    status: 'RETURNED',
    supplierName: 'Mega Suppliers',
    invoiceDate: '2026-09-12',
    grandTotal: '300.00',
  } as PurchaseInvoice,
];

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 1, email: 'owner@x.test', fullName: 'Owner', role: 'OWNER', companyId: 9 },
  }),
}));

vi.mock('@/api/resources', () => ({
  listPurchasesPage: async () => ({ results: ROWS, count: ROWS.length, next: null, previous: null }),
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

describe('PurchaseHistoryPage status badges — G-17 parity', () => {
  it('shows Returned for a fully-returned purchase invoice', async () => {
    wrap(<PurchaseHistoryPage />);
    const row = (await screen.findByText('PUR-0001')).closest('tr');
    expect(row).toBeTruthy();
    expect(within(row as HTMLElement).getByText(/returned/i)).toBeTruthy();
  });
});
