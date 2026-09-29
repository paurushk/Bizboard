import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
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

const getSalesInvoice = vi.fn(async (id: number | string) => {
  if (String(id) === '2') return PARTIAL_INVOICE;
  if (String(id) === '3') return LIVE_IRN_INVOICE;
  if (String(id) === '4') return DRAFT_INVOICE;
  return RETURNED_INVOICE;
});

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
  getInvoiceAudit: async () => [],
  listAllocationsPage: async () => ({ results: [], count: 0, next: null, previous: null }),
  listPaymentLinksPage: async () => ({ results: [], count: 0, next: null, previous: null }),
  listPaymentPromises: () => listPaymentPromises(),
  createPaymentPromise: (payload: Record<string, unknown>) => createPaymentPromise(payload),
  resolvePaymentPromise: (id: number) => resolvePaymentPromise(id),
  listSalesReturns: async () => [LINKED_RETURN],
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

  it('flags a partial return and lists the linked SalesReturn for auditability', async () => {
    wrap(<InvoiceDetailPage />, '/sales/history/2');
    await screen.findByText('INV-0002');
    expect(screen.getAllByText(/^completed$/i).length).toBeGreaterThan(0);
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
    await userEvent.click(screen.getByRole('button', { name: /^share$/i }));
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
