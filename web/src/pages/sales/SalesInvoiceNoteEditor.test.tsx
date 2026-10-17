import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { SalesInvoiceNoteEditor } from '@/pages/sales/SalesInvoiceNoteEditor';

// Credit / debit note editor: CN-01, CN-04 / DN-05, CN-05, CN-07, CN-08, CN-09 / DN-08, CN-10, CN-16,
// DEP-05, DN-07, NEW-09.
const OWNER = { id: 1, email: 'o@x.test', fullName: 'Owner', role: 'OWNER', companyId: 1 };
const ACCOUNTANT = { id: 2, email: 'a@x.test', fullName: 'Acct', role: 'ACCOUNTANT', companyId: 1 };
let currentUser: Record<string, unknown> = OWNER;
vi.mock('@/auth/AuthContext', () => ({ useAuth: () => ({ user: currentUser }) }));

const INVOICE = {
  id: 7,
  number: 'INV-7',
  status: 'COMPLETED',
  invoiceType: 'GST',
  customer: 3,
  customerName: 'Asha Stores',
  invoiceDate: '2026-02-10', // FY 2025-26: a credit note is due by 30 Nov 2026
  grandTotal: '118.00',
  items: [
    { id: 70, product: 5, productName: 'Widget', quantity: 2, unitPrice: 50, gstRate: 18, hsnCode: '8517' },
    { id: 71, product: 6, productName: 'Gadget', quantity: 1, unitPrice: 0, gstRate: 18, hsnCode: '' },
  ],
};

const getSalesInvoice = vi.fn(async (_id: number | string) => INVOICE);
const listSalesInvoicesPage = vi.fn(async (_p?: Record<string, unknown>) => ({
  results: [INVOICE], count: 1, next: null, previous: null,
}));
const summary = { invoiceId: 7, invoiceNumber: 'INV-7', grandTotal: '118.00', outstanding: '118.00' };
const getSummary = vi.fn(async (_id: number | string) => summary);
const filingDate = { fy: '2025-26', filedOn: null as string | null, noteDeadline: '2026-11-30' };
const getGstr9FilingDate = vi.fn(async (_fy: string) => filingDate);
const getSalesCreditNote = vi.fn();
const createSalesCreditNote = vi.fn(async (p: Record<string, unknown>) => ({ id: 99, status: 'DRAFT', ...p }));
const previewSalesTotals = vi.fn(async (p: Record<string, unknown>) => {
  const items = (p.items as Array<{ quantity: number; unitPrice: number }>) ?? [];
  const sum = items.reduce((s, i) => s + i.quantity * i.unitPrice, 0) * 1.18 + Number(p.additionalCharges ?? 0);
  return {
    subtotal: sum, discountTotal: 0, taxableTotal: sum, cgstTotal: 0, sgstTotal: 0, igstTotal: 0, cessTotal: 0,
    taxTotal: 0, roundOff: 0, grandTotal: sum, intraState: true, items: [],
  };
});

vi.mock('@/api/resources', () => ({
  getCompany: async () => ({ id: 1, gstin: '29AAAAA0000A1ZY', state: 'Karnataka' }),
  getCustomer: async () => ({ id: 3, name: 'Asha Stores', state: 'Karnataka', gstin: '29BBBBB1111B1Z5' }),
  getSalesInvoice: (id: number | string) => getSalesInvoice(id),
  getGstr9FilingDate: (fy: string) => getGstr9FilingDate(fy),
  listSalesInvoicesPage: (p?: Record<string, unknown>) => listSalesInvoicesPage(p),
  getSalesCreditNoteAdjustableSummary: (id: number | string) => getSummary(id),
  getSalesCreditNote: (id: number | string) => getSalesCreditNote(id),
  getSalesDebitNote: vi.fn(),
  createSalesCreditNote: (p: Record<string, unknown>) => createSalesCreditNote(p),
  createSalesDebitNote: vi.fn(),
  updateSalesCreditNote: vi.fn(),
  updateSalesDebitNote: vi.fn(),
  completeSalesCreditNote: vi.fn(),
  completeSalesDebitNote: vi.fn(),
  cancelSalesCreditNote: vi.fn(),
  cancelSalesDebitNote: vi.fn(),
  downloadSalesDocumentPdf: vi.fn(),
  previewSalesTotals: (p: Record<string, unknown>) => previewSalesTotals(p),
}));

function renderEditor(kind: 'credit' | 'debit', path: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const base = kind === 'credit' ? '/sales/credit-notes' : '/sales/debit-notes';
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path={`${base}/new`} element={<SalesInvoiceNoteEditor kind={kind} />} />
          <Route path={`${base}/:id`} element={<SalesInvoiceNoteEditor kind={kind} />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  currentUser = OWNER;
});
afterEach(() => {
  vi.clearAllMocks();
});

describe('credit note editor', () => {
  it('CN-16 — shows which invoice the note is against, with a link', async () => {
    renderEditor('credit', '/sales/credit-notes/new?fromInvoice=7');
    const link = await screen.findByRole('link', { name: 'INV-7' });
    expect(link.getAttribute('href')).toBe('/sales/history/7');
    expect(screen.getByText(/Asha Stores/)).toBeTruthy();
  });

  it('CN-10 — says stock is not restored and points to Sales Returns', async () => {
    renderEditor('credit', '/sales/credit-notes/new?fromInvoice=7');
    expect(await screen.findByText(/stock is not restored/i)).toBeTruthy();
    expect(screen.getByRole('link', { name: /open sales returns/i }).getAttribute('href')).toBe('/sales/returns');
  });

  it('CN-01 — does not offer "Sales return" as a reason on a new standalone note', async () => {
    renderEditor('credit', '/sales/credit-notes/new?fromInvoice=7');
    await screen.findByRole('link', { name: 'INV-7' });
    await userEvent.click(screen.getByRole('combobox', { name: /reason/i }));
    expect(await screen.findByRole('option', { name: /post-sale discount/i })).toBeTruthy();
    expect(screen.queryByRole('option', { name: /^sales return$/i })).toBeNull();
  });

  it('CN-08 — the shortcut button no longer promises a physical "Full return"', async () => {
    renderEditor('credit', '/sales/credit-notes/new?fromInvoice=7');
    expect(await screen.findByRole('button', { name: /credit full invoice value/i })).toBeTruthy();
    expect(screen.queryByRole('button', { name: /^full return$/i })).toBeNull();
  });

  it('CN-07 — limits the date to the Section 34(2) deadline and warns past it', async () => {
    renderEditor('credit', '/sales/credit-notes/new?fromInvoice=7');
    await screen.findByRole('link', { name: 'INV-7' });
    const date = screen.getByLabelText(/^date$/i) as HTMLInputElement;
    await waitFor(() => expect(date.max).toBe('2026-11-30'));
    expect(date.min).toBe('2026-02-10');
    fireEvent.change(date, { target: { value: '2026-12-15' } });
    expect(await screen.findByText(/past the section 34\(2\) limit.*2026-11-30/i)).toBeTruthy();
    fireEvent.change(date, { target: { value: '2026-01-01' } });
    expect(await screen.findByText(/cannot be before the invoice date/i)).toBeTruthy();
  });

  it('QOS-0127 — an earlier annual return filing date tightens the limit', async () => {
    filingDate.filedOn = '2026-10-15';
    filingDate.noteDeadline = '2026-10-15';
    try {
      renderEditor('credit', '/sales/credit-notes/new?fromInvoice=7');
      await screen.findByRole('link', { name: 'INV-7' });
      const date = screen.getByLabelText(/^date$/i) as HTMLInputElement;
      await waitFor(() => expect(date.max).toBe('2026-10-15'));
      expect(getGstr9FilingDate).toHaveBeenCalledWith('2025-26');
    } finally {
      filingDate.filedOn = null;
      filingDate.noteDeadline = '2026-11-30';
    }
  });

  it('QOS-0127 — a debit note has no s.34(2) limit and never asks for the filing date', async () => {
    getGstr9FilingDate.mockClear();
    renderEditor('debit', '/sales/debit-notes/new?fromInvoice=7');
    await screen.findByRole('link', { name: 'INV-7' });
    const date = screen.getByLabelText(/^date$/i) as HTMLInputElement;
    expect(date.max).toBe('');
    expect(getGstr9FilingDate).not.toHaveBeenCalled();
  });

  it('QOS-0127 — a failed filing-date lookup falls back to 30 November', async () => {
    getGstr9FilingDate.mockRejectedValueOnce(new Error('403'));
    renderEditor('credit', '/sales/credit-notes/new?fromInvoice=7');
    await screen.findByRole('link', { name: 'INV-7' });
    const date = screen.getByLabelText(/^date$/i) as HTMLInputElement;
    await waitFor(() => expect(date.max).toBe('2026-11-30'));
  });

  it('CN-05 — announces how much payment will move to the customer advance', async () => {
    summary.outstanding = '18.00'; // 100 of the 118 invoice is already paid
    try {
      renderEditor('credit', '/sales/credit-notes/new?fromInvoice=7');
      // Credit the full value: 2 x 50 + 18% = 118 against 18 outstanding.
      await userEvent.click(await screen.findByRole('button', { name: /credit full invoice value/i }));
      expect(await screen.findByText(/moves .*100.* of payments into the customer's advance/i)).toBeTruthy();
    } finally {
      summary.outstanding = '118.00';
    }
  });

  it('CN-05 — stays quiet when the invoice is unpaid', async () => {
    renderEditor('credit', '/sales/credit-notes/new?fromInvoice=7');
    await screen.findByRole('link', { name: 'INV-7' });
    expect(screen.queryByText(/payments into the customer's advance/i)).toBeNull();
  });

  it('DEP-05 — flags a line that has no HSN', async () => {
    renderEditor('credit', '/sales/credit-notes/new?fromInvoice=7');
    expect(await screen.findByRole('columnheader', { name: /hsn/i })).toBeTruthy();
    expect(await screen.findByText('8517')).toBeTruthy();
    expect(screen.getByText(/hsn missing/i)).toBeTruthy();
  });

  it('CN-04 — freight can be credited: the charge is sent and included in the preview', async () => {
    renderEditor('credit', '/sales/credit-notes/new?fromInvoice=7');
    await screen.findByRole('link', { name: 'INV-7' });
    await userEvent.click(await screen.findByRole('button', { name: /credit full invoice value/i }));
    expect(screen.queryByLabelText(/charges hsn/i)).toBeNull();
    await userEvent.type(screen.getByLabelText(/additional charges/i), '25');
    expect(await screen.findByLabelText(/charges hsn/i)).toBeTruthy();
    await waitFor(() => {
      const last = previewSalesTotals.mock.calls.at(-1)?.[0];
      expect(last).toMatchObject({ additionalCharges: 25 });
    });
  });

  it('CN-09 — searches invoices on the server, one small page, instead of loading all', async () => {
    renderEditor('credit', '/sales/credit-notes/new');
    await waitFor(() => expect(listSalesInvoicesPage).toHaveBeenCalled());
    expect(listSalesInvoicesPage.mock.calls[0][0]).toMatchObject({ page: 1, pageSize: 20, status: 'COMPLETED' });
    await userEvent.type(screen.getByRole('combobox', { name: /source invoice/i }), 'INV-7');
    await waitFor(() => {
      const last = listSalesInvoicesPage.mock.calls.at(-1)?.[0];
      expect(last).toMatchObject({ q: 'INV-7' });
    });
  });

  it('NEW-09 — a saved draft keeps each line pointed at its own invoice line', async () => {
    getSalesCreditNote.mockResolvedValue({
      id: 41, status: 'DRAFT', customer: 3, salesInvoice: 7, noteDate: '2026-09-01', reason: 'CORRECTION_OF_INVOICE',
      items: [{ id: 900, product: 5, productName: 'Widget', quantity: 1, unitPrice: 50, gstRate: 18, sourceItem: 70 }],
    });
    renderEditor('credit', '/sales/credit-notes/41');
    expect((await screen.findAllByText('Widget')).length).toBeGreaterThan(0);
    // The invoice line cap (2) is shown, not the note line id (900) or a guess.
    expect(await screen.findByText(/max 2/i)).toBeTruthy();
  });

  it('CN-01 — keeps the reason visible on a credit note a sales return issued', async () => {
    getSalesCreditNote.mockResolvedValue({
      id: 42, status: 'COMPLETED', customer: 3, salesInvoice: 7, noteDate: '2026-09-01', reason: 'SALES_RETURN',
      salesReturn: 12, items: [],
    });
    renderEditor('credit', '/sales/credit-notes/42');
    expect((await screen.findAllByText(/sales return/i)).length).toBeGreaterThan(0);
    expect(await screen.findByRole('link', { name: /cancel via sales return/i })).toBeTruthy();
    expect(screen.queryByRole('button', { name: /cancel document|^cancel$/i })).toBeNull();
  });
});

describe('credit note — refunding the advance it created (DEP-03)', () => {
  it('links straight to the refund for each receipt the note moved money into', async () => {
    getSalesCreditNote.mockResolvedValue({
      id: 43, status: 'COMPLETED', customer: 3, salesInvoice: 7, noteDate: '2026-09-01', reason: 'CORRECTION_OF_INVOICE',
      peeledReceiptAllocations: [{ receiptId: 31, amount: '60.00' }, { receiptId: 32, amount: '40.00' }, { receiptId: 31, amount: '5.00' }],
      items: [],
    });
    renderEditor('credit', '/sales/credit-notes/43');
    const links = await screen.findAllByRole('link', { name: /refund customer advance/i });
    expect(links.map((l) => l.getAttribute('href'))).toEqual(['/sales/receipts?refund=31', '/sales/receipts?refund=32']);
  });

  it('falls back to the receipts list when the note moved no money', async () => {
    getSalesCreditNote.mockResolvedValue({
      id: 44, status: 'COMPLETED', customer: 3, salesInvoice: 7, noteDate: '2026-09-01', reason: 'CORRECTION_OF_INVOICE',
      peeledReceiptAllocations: [], items: [],
    });
    renderEditor('credit', '/sales/credit-notes/44');
    const link = await screen.findByRole('link', { name: /refund customer advance/i });
    expect(link.getAttribute('href')).toBe('/sales/receipts');
  });
});

describe('debit note editor', () => {
  it('shows no stock or advance notices (those are credit-note effects)', async () => {
    renderEditor('debit', '/sales/debit-notes/new?fromInvoice=7');
    await screen.findByRole('link', { name: 'INV-7' });
    expect(screen.queryByText(/stock is not restored/i)).toBeNull();
    expect(screen.queryByRole('button', { name: /credit full invoice value/i })).toBeNull();
  });

  it('DN-08 — looks for completed and returned invoices, a page at a time', async () => {
    renderEditor('debit', '/sales/debit-notes/new');
    await waitFor(() => expect(listSalesInvoicesPage.mock.calls.length).toBeGreaterThanOrEqual(2));
    const statuses = listSalesInvoicesPage.mock.calls.map((c) => c[0]?.status);
    expect(statuses).toEqual(expect.arrayContaining(['COMPLETED', 'RETURNED']));
  });

  it('DN-05 — freight / interest can be billed on a debit note', async () => {
    renderEditor('debit', '/sales/debit-notes/new?fromInvoice=7');
    await screen.findByRole('link', { name: 'INV-7' });
    expect(screen.getByLabelText(/additional charges/i)).toBeTruthy();
  });

  it('DN-07 — the Owner can allow billing above the invoice value, and must give a reason', async () => {
    renderEditor('debit', '/sales/debit-notes/new?fromInvoice=7');
    await screen.findByRole('link', { name: 'INV-7' });
    const box = screen.getByRole('checkbox', { name: /allow billing more than the invoice value/i });
    expect(screen.queryByLabelText(/reason for billing above the invoice value/i)).toBeNull();
    await userEvent.click(box);
    expect(await screen.findByLabelText(/reason for billing above the invoice value/i)).toBeTruthy();
  });

  it('DN-07 — nobody but the Owner sees the override', async () => {
    currentUser = ACCOUNTANT;
    renderEditor('debit', '/sales/debit-notes/new?fromInvoice=7');
    await screen.findByRole('link', { name: 'INV-7' });
    expect(screen.queryByRole('checkbox', { name: /allow billing more than the invoice value/i })).toBeNull();
  });
});
