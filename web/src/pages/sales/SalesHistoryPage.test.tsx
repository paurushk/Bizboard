import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import type { ReactElement, ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { SalesHistoryPage } from '@/pages/sales/SalesHistoryPage';
import type { SalesInvoice } from '@/types/domain';

const listSalesInvoicesPage = vi.hoisted(() => vi.fn());

// G-17: the status badge on this list is computed client-side from three
// backend fields (status, balance, paymentState/returnState) — it must show
// the document's real lifecycle state even when other derived signals (a
// zeroed balance from an auto credit-note) would otherwise mask it. This
// pins the exact combinations that shipped a "Paid" badge on a fully-returned
// invoice (2026-09-12) and would mask a partial return with no badge at all.
const ROWS: SalesInvoice[] = [
  {
    id: 1,
    number: 'INV-0001',
    status: 'COMPLETED',
    customerName: 'Cash',
    invoiceDate: '2026-09-12',
    grandTotal: '104.00',
    balance: '0',
    paymentState: 'PAID',
    returnState: 'FULL',
  } as SalesInvoice,
  {
    id: 2,
    number: 'INV-0002',
    status: 'COMPLETED',
    customerName: 'Ravi Traders',
    invoiceDate: '2026-09-12',
    grandTotal: '500.00',
    balance: '200.00',
    paymentState: 'UNPAID',
    returnState: 'PARTIAL',
  } as SalesInvoice,
  {
    id: 3,
    number: 'INV-0003',
    status: 'COMPLETED',
    customerName: 'Sunita Traders',
    invoiceDate: '2026-09-12',
    grandTotal: '250.00',
    balance: '0',
    paymentState: 'PAID',
    returnState: 'NONE',
  } as SalesInvoice,
];

// This row's status is the point of the test: the backend flips it to
// RETURNED once every line is fully returned (return_service.py), but its
// outstanding balance nets to zero too (the auto credit-note unallocates the
// payment) — so paymentState comes back PAID from the same invoice. The old
// paidAwareStatus() checked paymentState first and rendered "Paid".
ROWS[0].status = 'RETURNED';
listSalesInvoicesPage.mockImplementation(async () => ({
  results: ROWS,
  count: ROWS.length,
  next: null,
  previous: null,
}));

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 1, email: 'owner@x.test', fullName: 'Owner', role: 'OWNER', companyId: 9 },
  }),
}));

vi.mock('@/api/resources', () => ({
  listSalesInvoicesPage: (...args: unknown[]) => listSalesInvoicesPage(...(args as [])),
  getInvoicePaymentStats: async () => ({
    paid: { count: 1, amount: '250' },
    partial: { count: 0, amount: '0' },
    unpaid: { count: 2, amount: '604' },
  }),
  shareInvoice: vi.fn(async () => ({ status: 'QUEUED' })),
  cancelSalesInvoice: vi.fn(),
  completeSalesInvoice: vi.fn(),
  deleteSalesInvoice: vi.fn(),
  downloadInvoicePdf: vi.fn(),
  downloadInvoiceThermalPdf: vi.fn(),
  bulkInvoicePdfZip: vi.fn(),
  recordInvoicePayment: vi.fn(),
}));

const navigate = vi.fn();
vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>();
  return { ...actual, useNavigate: () => navigate };
});

// jsdom has no real layout engine, so @tanstack/react-virtual's ResizeObserver-based
// sizing never reports a non-zero viewport and getVirtualItems() stays empty — every
// row would be windowed out. This page's own logic isn't under test here, so render
// every row unwindowed instead of reimplementing the virtualizer's measurement.
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

describe('SalesHistoryPage status badges — G-17', () => {
  it('shows Returned, not Paid, for a fully-returned invoice with a zeroed balance', async () => {
    wrap(<SalesHistoryPage />);
    const row = (await screen.findByText('INV-0001')).closest('tr');
    expect(row).toBeTruthy();
    expect(within(row as HTMLElement).getByText(/returned/i)).toBeTruthy();
    expect(within(row as HTMLElement).queryByText(/^paid$/i)).toBeNull();
  });

  it('flags a partial return with an extra chip while the invoice stays Completed/open-balance', async () => {
    wrap(<SalesHistoryPage />);
    const row = (await screen.findByText('INV-0002')).closest('tr');
    expect(row).toBeTruthy();
    expect(within(row as HTMLElement).getByText(/completed/i)).toBeTruthy();
    expect(within(row as HTMLElement).getByText(/partially returned/i)).toBeTruthy();
  });

  it('still shows Paid for a normal, non-returned, zero-balance invoice', async () => {
    wrap(<SalesHistoryPage />);
    const row = (await screen.findByText('INV-0003')).closest('tr');
    expect(row).toBeTruthy();
    expect(within(row as HTMLElement).getByText(/^paid$/i)).toBeTruthy();
    expect(within(row as HTMLElement).queryByText(/returned/i)).toBeNull();
  });
});

describe('SalesHistoryPage row actions', () => {
  it('opens the shared share dialog from the row menu', async () => {
    wrap(<SalesHistoryPage />);
    const row = (await screen.findByText('INV-0003')).closest('tr') as HTMLElement;
    await userEvent.click(within(row).getByRole('button', { name: /actions/i }));
    await userEvent.click(await screen.findByRole('menuitem', { name: /^share$/i }));
    expect(await screen.findByRole('dialog', { name: /share invoice/i })).toBeTruthy();
  });

  it('routes a completed invoice to sales return create with the invoice id', async () => {
    navigate.mockClear();
    wrap(<SalesHistoryPage />);
    const row = (await screen.findByText('INV-0003')).closest('tr') as HTMLElement;
    await userEvent.click(within(row).getByRole('button', { name: /actions/i }));
    await userEvent.click(await screen.findByRole('menuitem', { name: /sales return/i }));
    expect(navigate).toHaveBeenCalledWith('/sales/returns?create=1&invoice=3');
  });

  it('opens record payment from a row with an open balance', async () => {
    wrap(<SalesHistoryPage />);
    const row = (await screen.findByText('INV-0002')).closest('tr') as HTMLElement;
    await userEvent.click(within(row).getByRole('button', { name: /actions/i }));
    await userEvent.click(await screen.findByRole('menuitem', { name: /record payment/i }));
    expect(await screen.findByRole('dialog', { name: /record payment/i })).toBeTruthy();
  });
});

describe('SalesHistoryPage payment filter and stats', () => {
  it('shows payment-status chips and stats, and filters unpaid', async () => {
    listSalesInvoicesPage.mockClear();
    wrap(<SalesHistoryPage />);
    expect(await screen.findByText(/unpaid 2/i)).toBeTruthy();
    await userEvent.click(screen.getByRole('button', { name: /^unpaid$/i }));
    expect(listSalesInvoicesPage).toHaveBeenCalledWith(
      expect.objectContaining({ payment_status: 'UNPAID' }),
    );
  });
});
