import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import type { ReactElement } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { InvoiceDetailPage } from '@/pages/sales/InvoiceDetailPage';
import type { SalesInvoice, SalesReturn } from '@/types/domain';

// G-17: the header status chip on this page is computed client-side the same
// way as SalesHistoryPage's list badge — this pins the same combinations at
// the detail level, plus the "related returns" panel that links a partial
// return back to its invoice for auditability.
function baseInvoice(overrides: Partial<SalesInvoice>): SalesInvoice {
  return {
    id: 1,
    number: 'INV-0001',
    status: 'COMPLETED',
    invoiceType: 'RETAIL',
    customer: 3,
    customerName: 'Cash',
    invoiceDate: '2026-09-12',
    grandTotal: '104.00',
    subtotal: '104.00',
    discountTotal: '0',
    taxableTotal: '104.00',
    cgstTotal: '0',
    sgstTotal: '0',
    igstTotal: '0',
    roundOff: '0',
    balance: '0',
    received: '104.00',
    paymentState: 'PAID',
    returnState: 'NONE',
    items: [],
    ...overrides,
  } as SalesInvoice;
}

const RETURNED_INVOICE = baseInvoice({
  status: 'RETURNED',
  returnState: 'FULL',
  paymentState: 'PAID',
  balance: '0',
});

const PARTIAL_INVOICE = baseInvoice({
  id: 2,
  number: 'INV-0002',
  status: 'COMPLETED',
  returnState: 'PARTIAL',
  paymentState: 'UNPAID',
  balance: '200.00',
  grandTotal: '500.00',
});

const LINKED_RETURN: SalesReturn = {
  id: 9,
  number: 'SRN-0001',
  status: 'COMPLETED',
  customer: 3,
  salesInvoice: 2,
  returnDate: '2026-09-12',
  items: [],
  subtotal: '150.00',
  discountTotal: '0',
  taxableTotal: '150.00',
  cgstTotal: '0',
  sgstTotal: '0',
  igstTotal: '0',
  roundOff: '0',
  grandTotal: '150.00',
};

// G-GST-GUARD: OWNER is the default identity for every test in this file;
// the GST Guard override-permission tests below swap `currentUser` for the
// duration of a single test and the afterEach restores it so later tests in
// this file (and their fixed 'OWNER' expectations, e.g. CFT-116) aren't
// affected by ordering.
const OWNER_USER = { id: 1, email: 'owner@x.test', fullName: 'Owner', role: 'OWNER', companyId: 9 };
const SALES_STAFF_USER = {
  id: 2,
  email: 'staff@x.test',
  fullName: 'Staff',
  role: 'SALES_STAFF',
  companyId: 9,
  // canCreateSales is a separate capability flag from role — set so the
  // Complete button still renders for this non-owner/manager fixture.
  canCreateSales: true,
};
let currentUser: Record<string, unknown> = OWNER_USER;

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ user: currentUser }),
}));

const LIVE_IRN_INVOICE = baseInvoice({
  id: 3,
  number: 'INV-0003',
  status: 'COMPLETED',
  invoiceType: 'GST',
  einvoiceStatus: 'GENERATED',
  irn: 'IRN-LIVE',
});

const DRAFT_INVOICE = baseInvoice({
  id: 4,
  number: 'INV-0004',
  status: 'DRAFT',
  paymentState: 'UNPAID',
  balance: '104.00',
  received: '0',
});

const RECURRING_INVOICE = baseInvoice({
  id: 5,
  number: 'INV-0005',
  recurringOrigin: { scheduleId: 12, periodKey: '2026-Q4', isManual: false },
});

const getSalesInvoice = vi.fn(async (id: number | string) => {
  if (String(id) === '2') return PARTIAL_INVOICE;
  if (String(id) === '3') return LIVE_IRN_INVOICE;
  if (String(id) === '4') return DRAFT_INVOICE;
  if (String(id) === '5') return RECURRING_INVOICE;
  return RETURNED_INVOICE;
});

const noteRows = {
  credits: [] as Array<Record<string, unknown>>,
  debits: [] as Array<Record<string, unknown>>,
};

const completeSalesInvoice = vi.fn(async (_id: number, _options?: Record<string, unknown>) => RETURNED_INVOICE);
const listPaymentPromises = vi.fn(async () => [] as Array<Record<string, unknown>>);
const createPaymentPromise = vi.fn(async (payload: Record<string, unknown>) => ({
  id: 100,
  resolved: false,
  ...payload,
}));
const resolvePaymentPromise = vi.fn(async (id: number) => ({ id, resolved: true }));

vi.mock('@/api/resources', () => ({
  getSalesInvoice: (id: number | string) => getSalesInvoice(id),
  getCustomer: async () => ({ id: 3, name: 'Cash' }),
  getCompany: async () => ({ id: 9, einvoiceEnabled: true }),
  createInvoicePublicLink: vi.fn(async () => ({ url: 'https://example.test/i/tok' })),
  revokeInvoicePublicLink: vi.fn(),
  getInvoiceProfitDetails: vi.fn(),
  getInvoiceAudit: async () => [],
  listAllocationsPage: async () => ({ results: [], count: 0, next: null, previous: null }),
  listPaymentLinksPage: async () => ({ results: [], count: 0, next: null, previous: null }),
  listPaymentPromises: () => listPaymentPromises(),
  createPaymentPromise: (payload: Record<string, unknown>) => createPaymentPromise(payload),
  resolvePaymentPromise: (id: number) => resolvePaymentPromise(id),
  listSalesReturns: async () => [LINKED_RETURN],
  listSalesCreditNotesPage: async () => ({ results: noteRows.credits, count: noteRows.credits.length, next: null, previous: null }),
  listSalesDebitNotesPage: async () => ({ results: noteRows.debits, count: noteRows.debits.length, next: null, previous: null }),
  getSalesDocumentPdfStatus: async () => ({ pdfStatus: 'READY' }),
  downloadSalesDocumentPdf: vi.fn(),
  regenerateSalesDocumentPdf: vi.fn(),
  getUpiQr: vi.fn(),
  getInvoiceHsnSummary: async () => ({ invoiceId: 1, rows: [] }),
  getInvoiceProfitReport: async () => ({ rows: [] }),
  amendInvoiceFilingIdentity: vi.fn(),
  cancelSalesInvoice: vi.fn(),
  completeSalesInvoice: (id: number, options?: Record<string, unknown>) =>
    completeSalesInvoice(id, options),
  createPaymentLink: vi.fn(),
  cancelPaymentLink: vi.fn(),
  downloadInvoicePdf: vi.fn(),
  downloadInvoiceThermalPdf: vi.fn(),
  shareInvoice: vi.fn(),
  sharePaymentLink: vi.fn(),
  unallocatePayment: vi.fn(),
  updateSalesInvoice: vi.fn(),
  cancelInvoiceEinvoice: vi.fn(),
  cancelInvoiceEway: vi.fn(),
  markInvoiceEinvoiceGenerated: vi.fn(),
  markInvoiceEwayGenerated: vi.fn(),
  prepareInvoiceEinvoice: vi.fn(),
  prepareInvoiceEway: vi.fn(),
  submitInvoiceEinvoice: vi.fn(),
  submitInvoiceEway: vi.fn(),
}));

function wrap(ui: ReactElement, path: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/sales/history/:id" element={ui} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('InvoiceDetailPage status — G-17', () => {
  it('shows Returned, not Paid, for a fully-returned invoice', async () => {
    wrap(<InvoiceDetailPage />, '/sales/history/1');
    expect(await screen.findByText(/^returned$/i)).toBeTruthy();
    expect(screen.queryByText(/^paid$/i)).toBeNull();
  });

  it('links an invoice made by a recurring schedule back to the schedules page', async () => {
    wrap(<InvoiceDetailPage />, '/sales/history/5');
    const chip = await screen.findByRole('link', { name: /From a recurring schedule · 2026-Q4/ });
    expect(chip.getAttribute('href')).toBe('/sales/recurring');
  });

  it('flags a partial return and lists the linked SalesReturn for auditability', async () => {
    wrap(<InvoiceDetailPage />, '/sales/history/2');
    await screen.findByText('INV-0002');
    expect(screen.getAllByText(/^unpaid$/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/partially returned/i)).toBeTruthy();
    expect(await screen.findByText('SRN-0001')).toBeTruthy();
  });

  it('CFT-116 — Edit is disabled on the same screen as a live IRN', async () => {
    wrap(<InvoiceDetailPage />, '/sales/history/3');
    expect(await screen.findByText('INV-0003')).toBeTruthy();
    const edit = await screen.findByRole('button', { name: /^edit$/i });
    expect(edit).toBeDisabled();
    expect(screen.queryByRole('link', { name: /^edit$/i })).toBeNull();
    expect(
      await screen.findByText(/Line edits are blocked while this IRN is live/i),
    ).toBeTruthy();
  }, 15_000);

  it('opens the shared ShareInvoiceDialog from the detail share button', async () => {
    wrap(<InvoiceDetailPage />, '/sales/history/1');
    await screen.findByText('INV-0001');
    expect(screen.queryByRole('button', { name: /generate e-invoice/i })).toBeNull();
    await userEvent.click(screen.getByRole('button', { name: /^share$/i }));
    await userEvent.click(await screen.findByRole('menuitem', { name: /^whatsapp$/i }));
    expect(await screen.findByRole('dialog', { name: /share invoice/i })).toBeTruthy();
  });
});

// GST Guard: wired into the DRAFT -> Complete flow. A gst_guard_blocked
// error surfaces the blocking panel with an override reason field gated by
// canOverrideGstGuard (OWNER/MANAGER only); a successful complete can still
// carry non-blocking gstGuardWarnings, shown in a separate warning panel.
describe('InvoiceDetailPage — GST Guard on complete', () => {
  afterEach(() => {
    currentUser = OWNER_USER;
    completeSalesInvoice.mockReset();
  });

  it('blocks completion, shows the issue, and lets an OWNER override with a reason', async () => {
    const blockingIssue = { code: 'GSTIN_CHECKSUM_INVALID', message: 'Buyer GSTIN checksum is invalid.' };
    completeSalesInvoice
      .mockRejectedValueOnce({
        isAxiosError: true,
        response: {
          status: 409,
          data: { error: { code: 'gst_guard_blocked', details: { blocking: [blockingIssue] } } },
        },
      })
      .mockResolvedValueOnce({ ...DRAFT_INVOICE, status: 'COMPLETED' });

    wrap(<InvoiceDetailPage />, '/sales/history/4');
    await screen.findByText('INV-0004');
    await userEvent.click(screen.getByRole('button', { name: /^complete$/i }));

    expect(await screen.findByText('GST Guard blocked this invoice')).toBeTruthy();
    expect(screen.getByText(blockingIssue.message)).toBeTruthy();

    const reasonField = screen.getByLabelText(/reason for override/i);
    const overrideBtn = screen.getByRole('button', { name: /override and complete/i });
    expect(overrideBtn).toBeDisabled();

    await userEvent.type(reasonField, 'Verified GSTIN with buyer over call');
    expect(overrideBtn).not.toBeDisabled();

    await userEvent.click(overrideBtn);

    expect(completeSalesInvoice).toHaveBeenNthCalledWith(
      2,
      4,
      expect.objectContaining({ gstGuardOverrideReason: 'Verified GSTIN with buyer over call' }),
    );
  });

  it('does not offer an override to a non-owner/manager and shows the permission note instead', async () => {
    currentUser = SALES_STAFF_USER;
    const blockingIssue = { code: 'GSTIN_CHECKSUM_INVALID', message: 'Buyer GSTIN checksum is invalid.' };
    completeSalesInvoice.mockRejectedValueOnce({
      isAxiosError: true,
      response: {
        status: 409,
        data: { error: { code: 'gst_guard_blocked', details: { blocking: [blockingIssue] } } },
      },
    });

    wrap(<InvoiceDetailPage />, '/sales/history/4');
    await screen.findByText('INV-0004');
    await userEvent.click(screen.getByRole('button', { name: /^complete$/i }));

    expect(await screen.findByText('GST Guard blocked this invoice')).toBeTruthy();
    expect(screen.getByText(blockingIssue.message)).toBeTruthy();
    expect(screen.queryByLabelText(/reason for override/i)).toBeNull();
    expect(screen.queryByRole('button', { name: /override and complete/i })).toBeNull();
    expect(
      screen.getByText('Only an Owner or Manager can override a GST Guard block.'),
    ).toBeTruthy();
  });

  it('shows GST Guard warnings without blocking when completion succeeds', async () => {
    const warning = {
      code: 'HSN_NOT_IN_MASTER',
      message: "HSN '1905' was not found in the GST rate master.",
    };
    completeSalesInvoice.mockResolvedValueOnce({
      ...DRAFT_INVOICE,
      status: 'COMPLETED',
      gstGuardWarnings: [warning],
    });

    wrap(<InvoiceDetailPage />, '/sales/history/4');
    await screen.findByText('INV-0004');
    await userEvent.click(screen.getByRole('button', { name: /^complete$/i }));

    expect(await screen.findByText('GST Guard warnings')).toBeTruthy();
    expect(screen.getByText(warning.message)).toBeTruthy();
    expect(screen.queryByText('GST Guard blocked this invoice')).toBeNull();
  });
});

// Promise-to-pay: inline creation on the invoice detail page, gated by
// canManagePaymentPromises (OWNER/MANAGER/ACCOUNTANT). PARTIAL_INVOICE (id 2)
// has an outstanding balance and is reused across these cases; RETURNED_INVOICE
// (id 1, balance 0) covers the fully-paid case.
describe('InvoiceDetailPage — promise to pay', () => {
  afterEach(() => {
    currentUser = OWNER_USER;
    listPaymentPromises.mockReset();
    listPaymentPromises.mockResolvedValue([]);
    createPaymentPromise.mockClear();
    resolvePaymentPromise.mockClear();
  });

  it('lets an OWNER log a promise to pay on an invoice with an outstanding balance', async () => {
    wrap(<InvoiceDetailPage />, '/sales/history/2');
    await screen.findByText('INV-0002');

    const logBtn = await screen.findByRole('button', { name: /log a promise to pay/i });
    await userEvent.click(logBtn);

    const dialog = await screen.findByRole('dialog', { name: /log a promise to pay/i });
    fireEvent.change(within(dialog).getByLabelText(/promised date/i), {
      target: { value: '2026-10-05' },
    });
    fireEvent.change(within(dialog).getByLabelText(/note/i), {
      target: { value: 'Will pay after collections' },
    });
    await userEvent.click(within(dialog).getByRole('button', { name: /save promise/i }));

    expect(createPaymentPromise).toHaveBeenCalledWith(
      expect.objectContaining({
        customer: 3,
        invoice: 2,
        promisedDate: '2026-10-05',
        note: 'Will pay after collections',
      }),
    );
  });

  it('hides the action for a role without payment-promise permission', async () => {
    currentUser = SALES_STAFF_USER;
    wrap(<InvoiceDetailPage />, '/sales/history/2');
    await screen.findByText('INV-0002');
    expect(screen.queryByRole('button', { name: /log a promise to pay/i })).toBeNull();
  });

  it('shows an existing open promise instead of the create action, with a gated resolve action', async () => {
    listPaymentPromises.mockReset();
    listPaymentPromises
      .mockResolvedValueOnce([
        {
          id: 55,
          customer: 3,
          invoice: 2,
          promisedDate: '2026-10-01',
          note: 'Paying next week',
          resolved: false,
        },
      ])
      // After resolving, the invalidated query refetches — reflect the
      // now-resolved promise no longer being open.
      .mockResolvedValue([]);
    wrap(<InvoiceDetailPage />, '/sales/history/2');
    await screen.findByText('INV-0002');

    expect(await screen.findByText(/2026-10-01/)).toBeTruthy();
    expect(screen.getByText('Paying next week')).toBeTruthy();
    expect(screen.queryByRole('button', { name: /log a promise to pay/i })).toBeNull();

    await userEvent.click(screen.getByRole('button', { name: /mark as resolved/i }));
    expect(resolvePaymentPromise).toHaveBeenCalledWith(55);
  });

  it('hides the resolve action for the existing promise for a role without permission', async () => {
    currentUser = SALES_STAFF_USER;
    listPaymentPromises.mockReset();
    listPaymentPromises.mockResolvedValueOnce([
      {
        id: 55,
        customer: 3,
        invoice: 2,
        promisedDate: '2026-10-01',
        note: 'Paying next week',
        resolved: false,
      },
    ]);
    wrap(<InvoiceDetailPage />, '/sales/history/2');
    await screen.findByText('INV-0002');
    expect(screen.queryByText(/2026-10-01/)).toBeNull();
    expect(screen.queryByRole('button', { name: /mark as resolved/i })).toBeNull();
  });

  it('does not show the promise-to-pay action on a fully-paid invoice', async () => {
    wrap(<InvoiceDetailPage />, '/sales/history/1');
    await screen.findByText('INV-0001');
    expect(screen.queryByRole('button', { name: /log a promise to pay/i })).toBeNull();
    expect(screen.queryByText(/promise to pay/i)).toBeNull();
  });
});

describe('InvoiceDetailPage — return goods entry point (SR-04)', () => {
  function Destination({ label }: { label: string }) {
    const location = useLocation();
    return <div data-testid={label}>{location.pathname + location.search}</div>;
  }

  function wrapWithDestinations(path: string) {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    return render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={[path]}>
          <Routes>
            <Route path="/sales/history/:id" element={<InvoiceDetailPage />} />
            <Route path="/sales/returns" element={<Destination label="returns" />} />
            <Route path="/sales/credit-notes/new" element={<Destination label="credit-note" />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
  }

  async function openMore() {
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: /^more$/i }));
    return user;
  }

  it('routes "Return goods" to Sales Returns, which moves stock', async () => {
    wrapWithDestinations('/sales/history/2');
    const user = await openMore();
    await user.click(await screen.findByRole('menuitem', { name: /return goods/i }));
    expect((await screen.findByTestId('returns')).textContent).toBe('/sales/returns?create=1&invoice=2');
  });

  it('offers a separate "New credit note" for value-only adjustments', async () => {
    wrapWithDestinations('/sales/history/2');
    const user = await openMore();
    await user.click(await screen.findByRole('menuitem', { name: /new credit note/i }));
    expect((await screen.findByTestId('credit-note')).textContent).toBe('/sales/credit-notes/new?fromInvoice=2');
  });

  it('does not offer "Return goods" on a fully returned invoice', async () => {
    wrapWithDestinations('/sales/history/1');
    await openMore();
    await screen.findByRole('menuitem', { name: /new credit note/i });
    expect(screen.queryByRole('menuitem', { name: /return goods/i })).toBeNull();
  });
});


// Credit / debit notes plan: DN-01 (New Debit Note action) and DEP-01 (notes on the invoice).
describe('InvoiceDetailPage — credit and debit notes', () => {
  afterEach(() => {
    currentUser = OWNER_USER;
    noteRows.credits = [];
    noteRows.debits = [];
  });

  it('DN-01 — offers New Debit Note beside New Credit Note, pre-filled with this invoice', async () => {
    wrap(<InvoiceDetailPage />, '/sales/history/2');
    await screen.findByText('INV-0002');
    await userEvent.click(screen.getByRole('button', { name: /^more$/i }));
    const debit = await screen.findByRole('menuitem', { name: /new debit note/i });
    expect(debit.getAttribute('href')).toBe('/sales/debit-notes/new?fromInvoice=2');
    const credit = screen.getByRole('menuitem', { name: /new credit note/i });
    expect(credit.getAttribute('href')).toBe('/sales/credit-notes/new?fromInvoice=2');
  });

  it('DN-01 — hides New Debit Note from a user who cannot issue notes', async () => {
    currentUser = { id: 5, email: 'v@x.test', fullName: 'View', role: 'VIEWER', companyId: 9 };
    wrap(<InvoiceDetailPage />, '/sales/history/2');
    await screen.findByText('INV-0002');
    await userEvent.click(screen.getByRole('button', { name: /^more$/i }));
    expect(screen.queryByRole('menuitem', { name: /new debit note/i })).toBeNull();
  });

  it('DEP-01 — says so when the invoice has no notes', async () => {
    wrap(<InvoiceDetailPage />, '/sales/history/2');
    const section = await screen.findByTestId('invoice-notes-section');
    expect(await within(section).findByText(/no credit or debit notes on this invoice/i)).toBeTruthy();
  });

  it('DEP-01 — lists notes and the net amount (credits reduce, debits increase)', async () => {
    noteRows.credits = [
      { id: 11, number: 'SCN-1', status: 'COMPLETED', noteDate: '2026-09-13', grandTotal: '100.00' },
      { id: 12, number: 'SCN-2', status: 'CANCELLED', noteDate: '2026-09-14', grandTotal: '999.00' },
    ];
    noteRows.debits = [
      { id: 21, number: 'SDN-1', status: 'COMPLETED', noteDate: '2026-09-15', grandTotal: '30.00' },
    ];
    wrap(<InvoiceDetailPage />, '/sales/history/2');
    const section = await screen.findByTestId('invoice-notes-section');
    expect(await within(section).findByText('SCN-1')).toBeTruthy();
    expect(within(section).getByText('SDN-1')).toBeTruthy();
    expect(within(section).getByRole('link', { name: 'SCN-1' }).getAttribute('href')).toBe('/sales/credit-notes/11');
    expect(within(section).getByRole('link', { name: 'SDN-1' }).getAttribute('href')).toBe('/sales/debit-notes/21');
    // 500 invoice - 100 completed credit + 30 completed debit; the cancelled 999 is ignored.
    expect(within(section).getByText(/430/)).toBeTruthy();
  });
});
