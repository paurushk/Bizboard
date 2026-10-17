import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
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

const { listPurchasesPage } = vi.hoisted(() => ({ listPurchasesPage: vi.fn() }));

vi.mock('@/api/resources', () => ({
  listCustomersPage: async () => ({ count: 0, next: null, previous: null, results: [] }),
  listSuppliersPage: async () => ({ count: 0, next: null, previous: null, results: [] }),
  listPurchasesPage: (...args: unknown[]) => listPurchasesPage(...args),
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

function wrap(ui: ReactElement, path = '/') {
  listPurchasesPage.mockResolvedValue({ results: ROWS, count: ROWS.length, next: null, previous: null });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>{ui}</MemoryRouter>
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

describe('PurchaseHistoryPage opened from the Money hub', () => {
  it('opens on overdue bills and asks the server for exactly those', async () => {
    wrap(<PurchaseHistoryPage />, '/purchases/history?overdue=1&via=money');
    expect(await screen.findByText('Opened from Money: Overdue to suppliers')).toBeTruthy();
    expect(listPurchasesPage).toHaveBeenCalledWith(expect.objectContaining({ overdue: 1 }));
    expect(screen.getByRole('button', { name: 'Overdue to suppliers', pressed: true })).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Back to Money' }).getAttribute('href')).toBe('/money');
  });

  it('opens on bills due in 7 days', async () => {
    wrap(<PurchaseHistoryPage />, '/purchases/history?due_soon=1&via=money');
    await screen.findByText('PUR-0001');
    expect(listPurchasesPage).toHaveBeenCalledWith(expect.objectContaining({ due_soon: 1 }));
    expect(screen.getByRole('button', { name: 'Due in 7 days', pressed: true })).toBeTruthy();
  });

  it('opens on bills still owed, for one supplier', async () => {
    wrap(<PurchaseHistoryPage />, '/purchases/history?has_balance=1&supplier=4&via=money');
    await screen.findByText('PUR-0001');
    expect(listPurchasesPage).toHaveBeenCalledWith(expect.objectContaining({ has_balance: 1, supplier: 4 }));
    expect(screen.getByText('One supplier')).toBeTruthy();
  });

  it('switches the money filter from the page, and off again', async () => {
    wrap(<PurchaseHistoryPage />);
    await screen.findByText('PUR-0001');
    expect(listPurchasesPage).toHaveBeenLastCalledWith(expect.not.objectContaining({ overdue: 1 }));
    await userEvent.click(screen.getByRole('button', { name: 'Overdue to suppliers' }));
    await waitFor(() => expect(listPurchasesPage).toHaveBeenLastCalledWith(expect.objectContaining({ overdue: 1 })));
    await userEvent.click(screen.getByRole('button', { name: 'Overdue to suppliers' }));
    await waitFor(() => expect(listPurchasesPage).toHaveBeenLastCalledWith(expect.not.objectContaining({ overdue: 1 })));
  });

  it('drops the hub filter and the bar when asked to show everything', async () => {
    wrap(<PurchaseHistoryPage />, '/purchases/history?overdue=1&supplier=4&via=money');
    await screen.findByText('Opened from Money: Overdue to suppliers');
    await userEvent.click(screen.getByRole('button', { name: 'Show everything' }));
    await waitFor(() => expect(screen.queryByText(/Opened from Money/)).toBeNull());
    await waitFor(() =>
      expect(listPurchasesPage).toHaveBeenLastCalledWith(
        expect.not.objectContaining({ overdue: 1 }),
      ),
    );
    expect(listPurchasesPage).toHaveBeenLastCalledWith(expect.not.objectContaining({ supplier: 4 }));
  });

  it('has no hand-off bar when opened directly', async () => {
    wrap(<PurchaseHistoryPage />);
    await screen.findByText('PUR-0001');
    expect(screen.queryByText(/Opened from Money/)).toBeNull();
  });
});
