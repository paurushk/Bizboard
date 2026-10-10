import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, RouterProvider, createBrowserRouter, createMemoryRouter } from 'react-router-dom';
import type { ReactElement, ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { SalesHistoryPage } from '@/pages/sales/SalesHistoryPage';
import type { SalesInvoice } from '@/types/domain';

const listSalesInvoicesPage = vi.hoisted(() => vi.fn());
const bulkInvoicePdfZip = vi.hoisted(() => vi.fn());
const downloadBulkInvoicePdfZip = vi.hoisted(() => vi.fn());
const triggerBlobDownload = vi.hoisted(() => vi.fn());
const cancelSalesInvoiceMock = vi.hoisted(() => vi.fn());
const exportSalesRegisterCsv = vi.hoisted(() => vi.fn());

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
  listCustomersPage: async () => ({ count: 0, next: null, previous: null, results: [] }),
  getCustomer: async (id: number) => ({ id: Number(id), name: 'Gopal', status: 'ACTIVE' }),
  listSuppliersPage: async () => ({ count: 0, next: null, previous: null, results: [] }),
  listSalesInvoicesPage: (...args: unknown[]) => listSalesInvoicesPage(...(args as [])),
  getInvoicePaymentStats: async () => ({
    paid: { count: 1, amount: '250' },
    partial: { count: 0, amount: '0' },
    unpaid: { count: 2, amount: '604' },
  }),
  shareInvoice: vi.fn(async () => ({ status: 'QUEUED' })),
  cancelSalesInvoice: (...args: unknown[]) => cancelSalesInvoiceMock(...(args as [])),
  completeSalesInvoice: vi.fn(),
  deleteSalesInvoice: vi.fn(),
  downloadInvoicePdf: vi.fn(),
  downloadInvoiceThermalPdf: vi.fn(),
  bulkInvoicePdfZip: (...args: unknown[]) => bulkInvoicePdfZip(...(args as [])),
  downloadBulkInvoicePdfZip: (...args: unknown[]) => downloadBulkInvoicePdfZip(...(args as [])),
  recordInvoicePayment: vi.fn(),
  exportSalesRegisterCsv: (...args: unknown[]) => exportSalesRegisterCsv(...(args as [])),
}));

vi.mock('@/utils/blob', () => ({
  printBlob: vi.fn(),
  triggerBlobDownload: (...args: unknown[]) => triggerBlobDownload(...(args as [])),
}));

vi.mock('@/components/RecordInvoicePaymentDialog', () => ({
  RecordInvoicePaymentDialog: ({ open, onSuccess }: { open: boolean; onSuccess: () => void }) =>
    open ? (
      <div role="dialog" aria-label="Record payment">
        <button type="button" onClick={onSuccess}>
          Save payment
        </button>
      </div>
    ) : null,
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

function wrap(ui: ReactElement, entries = ['/sales/history']) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={entries}>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

function renderWithHistory(entries: string[]) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createMemoryRouter([{ path: '/sales/history', element: <SalesHistoryPage /> }], {
    initialEntries: entries,
  });
  render(
    <QueryClientProvider client={qc}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return router;
}

describe('SalesHistoryPage status badges — G-17', () => {
  it('shows Returned, not Paid, for a fully-returned invoice with a zeroed balance', async () => {
    wrap(<SalesHistoryPage />);
    const row = (await screen.findByText(/INV-(?:0001|1)/)).closest('tr');
    expect(row).toBeTruthy();
    expect(within(row as HTMLElement).getByText(/returned/i)).toBeTruthy();
    expect(within(row as HTMLElement).queryByText(/^paid$/i)).toBeNull();
  });

  it('flags a partial return with an extra chip while the invoice stays Completed/open-balance', async () => {
    wrap(<SalesHistoryPage />);
    const row = (await screen.findByText(/INV-(?:0002|2)/)).closest('tr');
    expect(row).toBeTruthy();
    expect(within(row as HTMLElement).getByText(/unpaid/i)).toBeTruthy();
    expect(within(row as HTMLElement).getByText(/partially returned/i)).toBeTruthy();
  });

  it('still shows Paid for a normal, non-returned, zero-balance invoice', async () => {
    wrap(<SalesHistoryPage />);
    const row = (await screen.findByText(/INV-(?:0003|3)/)).closest('tr');
    expect(row).toBeTruthy();
    expect(within(row as HTMLElement).getByText(/^paid$/i)).toBeTruthy();
    expect(within(row as HTMLElement).queryByText(/returned/i)).toBeNull();
  });
});

describe('SalesHistoryPage row actions', () => {
  it('opens the shared share dialog from the row menu', async () => {
    wrap(<SalesHistoryPage />);
    const row = (await screen.findByText(/INV-(?:0003|3)/)).closest('tr') as HTMLElement;
    await userEvent.click(within(row).getByRole('button', { name: /actions/i }));
    await userEvent.click(await screen.findByRole('menuitem', { name: /^share$/i }));
    expect(await screen.findByRole('dialog', { name: /share invoice/i })).toBeTruthy();
  });

  it('routes a completed invoice to sales return create with the invoice id', async () => {
    navigate.mockClear();
    wrap(<SalesHistoryPage />);
    const row = (await screen.findByText(/INV-(?:0003|3)/)).closest('tr') as HTMLElement;
    await userEvent.click(within(row).getByRole('button', { name: /actions/i }));
    await userEvent.click(await screen.findByRole('menuitem', { name: /sales return/i }));
    expect(navigate).toHaveBeenCalledWith('/sales/returns?create=1&invoice=3');
  });

  it('opens record payment from a row with an open balance', async () => {
    wrap(<SalesHistoryPage />);
    const row = (await screen.findByText(/INV-(?:0002|2)/)).closest('tr') as HTMLElement;
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
    await userEvent.click(screen.getByRole('button', { name: /unpaid 2/i }));
    expect(listSalesInvoicesPage).toHaveBeenCalledWith(
      expect.objectContaining({ payment_status: 'UNPAID' }),
    );
  });
});

describe('SalesHistoryPage accessibility', () => {
  it('has no serious or critical axe violations on the rendered register', async () => {
    const axe = (await import('axe-core')).default;
    const { container } = wrap(<SalesHistoryPage />);
    await screen.findByText(/INV-(?:0003|3)/);
    const result = await axe.run(container, {
      rules: { 'color-contrast': { enabled: false }, region: { enabled: false } },
    });
    const blocking = result.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical');
    expect(blocking.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(' ')).join(', ')}`)).toEqual([]);
  });

  it('cancel asks for a reason and returns focus to the row actions button on close', async () => {
    wrap(<SalesHistoryPage />);
    const row = (await screen.findByText(/INV-(?:0003|3)/)).closest('tr') as HTMLElement;
    const actions = within(row).getByRole('button', { name: /actions/i });
    await userEvent.click(actions);
    await userEvent.click(await screen.findByRole('menuitem', { name: /^cancel$/i }));
    const dialog = await screen.findByRole('dialog', { name: /cancel/i });
    const confirm = within(dialog).getByRole('button', { name: /cancel invoice/i });
    expect((confirm as HTMLButtonElement).disabled).toBe(true);
    await userEvent.type(within(dialog).getByLabelText(/reason/i), 'wrong bill');
    expect((confirm as HTMLButtonElement).disabled).toBe(false);
    await userEvent.keyboard('{Escape}');
    await vi.waitFor(() => expect(document.activeElement).toBe(actions));
  });
});

describe('SalesHistoryPage address bar', () => {
  it('sends the unpaid filter and customer id from the URL and shows that customer', async () => {
    listSalesInvoicesPage.mockClear();
    wrap(<SalesHistoryPage />, ['/sales/history?payment=UNPAID&customer=9']);
    expect(await screen.findByDisplayValue('Gopal')).toBeTruthy();
    expect(listSalesInvoicesPage).toHaveBeenCalledWith(
      expect.objectContaining({ payment_status: 'UNPAID', customer: 9 }),
    );
  });

  it('replaces the search query so Back restores the previous filter', async () => {
    const router = renderWithHistory(['/sales/history?status=DRAFT', '/sales/history']);
    const search = await screen.findByLabelText(/bill number, customer, or phone/i);
    await userEvent.type(search, 'abc');
    await vi.waitFor(() => expect(router.state.location.search).toBe('?q=abc'));
    expect(router.state.historyAction).toBe('REPLACE');
    await router.navigate(-1);
    await vi.waitFor(() => expect(router.state.location.search).toBe('?status=DRAFT'));
    await new Promise((r) => setTimeout(r, 400));
    expect(router.state.location.search).toBe('?status=DRAFT');
  });

  it('Back pressed while a search is still pending is not overwritten by it', async () => {
    window.history.replaceState(null, '', '/sales/history?status=DRAFT');
    window.history.pushState(null, '', '/sales/history');
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const router = createBrowserRouter([{ path: '/sales/history', element: <SalesHistoryPage /> }]);
    render(
      <QueryClientProvider client={qc}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    );
    const search = await screen.findByLabelText(/bill number, customer, or phone/i);
    await userEvent.type(search, 'x');
    await router.navigate(-1);
    await vi.waitFor(() => expect(router.state.location.search).toBe('?status=DRAFT'));
    await new Promise((r) => setTimeout(r, 400));
    expect(router.state.location.search).toBe('?status=DRAFT');
  });
});

describe('SalesHistoryPage bulk download', () => {
  it('downloads the zip through the API and names the skipped bills', async () => {
    bulkInvoicePdfZip.mockResolvedValueOnce({
      url: 'http://api.test/media/company_9/export/x.zip',
      fileId: 77,
      included: [{ id: 3, number: 'INV-0003' }],
      skipped: [{ id: 2, number: 'INV-0002', reason: 'not_completed' }],
    });
    const blob = new Blob(['zip']);
    downloadBulkInvoicePdfZip.mockResolvedValueOnce(blob);
    wrap(<SalesHistoryPage />);
    const row = (await screen.findByText(/INV-(?:0003|3)/)).closest('tr') as HTMLElement;
    await userEvent.click(within(row).getByRole('checkbox'));
    await userEvent.click(screen.getByRole('button', { name: /download pdfs/i }));
    await vi.waitFor(() => expect(triggerBlobDownload).toHaveBeenCalledWith(blob, 'invoices.zip'));
    expect(downloadBulkInvoicePdfZip).toHaveBeenCalledWith(77);
    expect(await screen.findByText(/skipped: INV-0002/i)).toBeTruthy();
    expect((await screen.findByRole('alert')).className).toMatch(/Warning/);
  });

  it('a download with nothing skipped reports success', async () => {
    bulkInvoicePdfZip.mockResolvedValueOnce({
      url: '',
      fileId: 78,
      included: [{ id: 3, number: 'INV-0003' }],
      skipped: [],
    });
    downloadBulkInvoicePdfZip.mockResolvedValueOnce(new Blob(['zip']));
    wrap(<SalesHistoryPage />);
    const row = (await screen.findByText(/INV-(?:0003|3)/)).closest('tr') as HTMLElement;
    await userEvent.click(within(row).getByRole('checkbox'));
    await userEvent.click(screen.getByRole('button', { name: /download pdfs/i }));
    await vi.waitFor(() => expect(downloadBulkInvoicePdfZip).toHaveBeenCalledWith(78));
    const alert = await screen.findByRole('alert');
    expect(alert.className).toMatch(/Success/);
    expect(alert.textContent).not.toMatch(/skipped/i);
  });
});

describe('SalesHistoryPage messages', () => {
  async function openRowAction(number: RegExp, action: RegExp) {
    const row = (await screen.findByText(number)).closest('tr') as HTMLElement;
    await userEvent.click(within(row).getByRole('button', { name: /actions/i }));
    await userEvent.click(await screen.findByRole('menuitem', { name: action }));
  }

  it('recording a payment names the bill in a success message', async () => {
    wrap(<SalesHistoryPage />);
    await openRowAction(/INV-(?:0002|2)/, /record payment/i);
    await userEvent.click(within(await screen.findByRole('dialog', { name: /record payment/i })).getByRole('button', { name: /save payment/i }));
    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toMatch(/payment recorded for INV-0002/i);
    expect(alert.className).toMatch(/Success/);
    expect(screen.queryByRole('dialog', { name: /record payment/i })).toBeNull();
  });

  it('a success after a pending-approval warning is shown as a success', async () => {
    cancelSalesInvoiceMock.mockResolvedValueOnce({ outcome: 'pending', invoiceId: 3, approvalId: 5 });
    wrap(<SalesHistoryPage />);
    await openRowAction(/INV-(?:0003|3)/, /^cancel$/i);
    const dialog = await screen.findByRole('dialog', { name: /cancel/i });
    await userEvent.type(within(dialog).getByLabelText(/reason/i), 'wrong bill');
    await userEvent.click(within(dialog).getByRole('button', { name: /cancel invoice/i }));
    const pending = await screen.findByText(/waiting for approval/i);
    expect(pending.closest('[role="alert"]')?.className).toMatch(/Warning/);
    expect(cancelSalesInvoiceMock).toHaveBeenCalledWith(3, { reason: 'wrong bill' });
    // The closing dialog hides the rest of the page from assistive tech until it has gone.
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());

    await openRowAction(/INV-(?:0002|2)/, /record payment/i);
    await userEvent.click(within(await screen.findByRole('dialog', { name: /record payment/i })).getByRole('button', { name: /save payment/i }));
    const recorded = await screen.findByText(/payment recorded for INV-0002/i);
    expect(recorded.closest('[role="alert"]')?.className).toMatch(/Success/);
  });
});

describe('SalesHistoryPage review fixes', () => {
  it('keeps the filters on screen when the list fails to load', async () => {
    listSalesInvoicesPage.mockRejectedValueOnce(new Error('boom'));
    wrap(<SalesHistoryPage />);
    expect(await screen.findByRole('button', { name: /retry/i })).toBeTruthy();
    expect(screen.getByLabelText(/bill number, customer, or phone/i)).toBeTruthy();
    expect(screen.getByRole('button', { name: /unpaid 2/i })).toBeTruthy();
  });

  it('sort headers cycle newest, highest first, lowest first, then the default, with aria-sort', async () => {
    listSalesInvoicesPage.mockClear();
    wrap(<SalesHistoryPage />);
    await screen.findByText(/INV-(?:0003|3)/);
    const header = screen.getByRole('columnheader', { name: /total/i });
    expect(header.getAttribute('aria-sort')).toBe('none');
    await userEvent.click(within(header).getByRole('button'));
    await vi.waitFor(() => expect(listSalesInvoicesPage).toHaveBeenLastCalledWith(expect.objectContaining({ sort: 'total_desc' })));
    expect(screen.getByRole('columnheader', { name: /total/i }).getAttribute('aria-sort')).toBe('descending');
    await userEvent.click(within(screen.getByRole('columnheader', { name: /total/i })).getByRole('button'));
    await vi.waitFor(() => expect(listSalesInvoicesPage).toHaveBeenLastCalledWith(expect.objectContaining({ sort: 'total_asc' })));
    await userEvent.click(within(screen.getByRole('columnheader', { name: /total/i })).getByRole('button'));
    await vi.waitFor(() => expect(listSalesInvoicesPage).toHaveBeenLastCalledWith(expect.objectContaining({ sort: 'date_desc' })));
  });

  it('a refused cancel closes the dialog and shows the server message', async () => {
    cancelSalesInvoiceMock.mockRejectedValueOnce(new Error('A receipt is still allocated.'));
    wrap(<SalesHistoryPage />);
    const row = (await screen.findByText(/INV-(?:0003|3)/)).closest('tr') as HTMLElement;
    await userEvent.click(within(row).getByRole('button', { name: /actions/i }));
    await userEvent.click(await screen.findByRole('menuitem', { name: /^cancel$/i }));
    const dialog = await screen.findByRole('dialog', { name: /cancel/i });
    await userEvent.type(within(dialog).getByLabelText(/reason/i), 'wrong bill');
    await userEvent.click(within(dialog).getByRole('button', { name: /cancel invoice/i }));
    expect(await screen.findByText(/receipt is still allocated/i)).toBeTruthy();
    await vi.waitFor(() => expect(screen.queryByRole('dialog', { name: /cancel/i })).toBeNull());
  });

  it('hides Cancel while a cancel approval is already pending', async () => {
    listSalesInvoicesPage.mockResolvedValueOnce({
      results: [{ ...ROWS[2], cancelApprovalPending: true }],
      count: 1, next: null, previous: null,
    });
    wrap(<SalesHistoryPage />);
    const row = (await screen.findByText(/INV-(?:0003|3)/)).closest('tr') as HTMLElement;
    await userEvent.click(within(row).getByRole('button', { name: /actions/i }));
    await screen.findByRole('menuitem', { name: /^open$/i });
    expect(screen.queryByRole('menuitem', { name: /^cancel$/i })).toBeNull();
  });

  it('the Overdue chip filters, shows in the URL, and the CSV export keeps the filters', async () => {
    listSalesInvoicesPage.mockClear();
    const blob = new Blob(['csv']);
    exportSalesRegisterCsv.mockResolvedValueOnce(blob);
    triggerBlobDownload.mockClear();
    const router = renderWithHistory(['/sales/history?payment=UNPAID']);
    await screen.findByText(/INV-(?:0003|3)/);
    await userEvent.click(screen.getByRole('button', { name: /^overdue$/i }));
    await vi.waitFor(() => expect(router.state.location.search).toContain('overdue=1'));
    await vi.waitFor(() => expect(listSalesInvoicesPage).toHaveBeenLastCalledWith(expect.objectContaining({ overdue: 1, payment_status: 'UNPAID' })));
    await userEvent.click(screen.getByRole('button', { name: /export csv/i }));
    await vi.waitFor(() => expect(triggerBlobDownload).toHaveBeenCalledWith(blob, 'sales-register.csv'));
    expect(exportSalesRegisterCsv).toHaveBeenCalledWith(expect.objectContaining({ overdue: 1, payment_status: 'UNPAID' }));
  });

  it('a link past the last page returns to page 1 instead of staying on the error', async () => {
    const gone = Object.assign(new Error('Invalid page.'), { isAxiosError: true, response: { status: 404 } });
    listSalesInvoicesPage.mockRejectedValueOnce(gone);
    const router = renderWithHistory(['/sales/history?page=9']);
    await vi.waitFor(() => expect(router.state.location.search).not.toContain('page=9'));
    expect(await screen.findByText(/INV-(?:0003|3)/)).toBeTruthy();
  });
});
