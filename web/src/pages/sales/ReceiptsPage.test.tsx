import 'fake-indexeddb/auto';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import axe from 'axe-core';
import { MemoryRouter } from 'react-router-dom';
import type { ReactElement } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ReceiptsPage } from '@/pages/sales/ReceiptsPage';
import type { CustomerReceipt } from '@/types/domain';

const {
  RECEIPT,
  VOIDED,
  setReceiptChequeStatus,
  voidReceipt,
  trackShopFloor,
  listReceiptsPage,
  getReceiptsSummary,
  exportReceiptsCsv,
  fetchReceiptVoucher,
  createReceipt,
  printBlob,
  triggerBlobDownload,
} = vi.hoisted(() => {
  const receipt: CustomerReceipt = {
    id: 44,
    number: 'RCT-0001',
    customer: 3,
    customerName: 'Ravi Traders',
    amount: '100.00',
    mode: 'CHEQUE',
    receiptDate: '2026-09-22',
    allocated: '0',
    unallocated: '100.00',
    status: 'POSTED',
    source: 'MANUAL',
    chequeNumber: '123456',
    chequeBankName: 'HDFC',
    chequeStatus: 'PENDING_CLEARANCE',
    allocationLines: [],
  };
  const voided: CustomerReceipt = {
    id: 45,
    number: 'RCT-0002',
    customer: 4,
    customerName: 'Anil Store',
    amount: '60.00',
    mode: 'CASH',
    receiptDate: '2026-09-23',
    allocated: '0',
    unallocated: '60.00',
    status: 'VOIDED',
    source: 'MANUAL',
    voidReason: 'entered twice',
    voidedByName: 'Owner',
    allocationLines: [],
  };
  return {
    RECEIPT: receipt,
    VOIDED: voided,
    setReceiptChequeStatus: vi.fn(async () => ({ ...receipt, chequeStatus: 'CLEARED' })),
    voidReceipt: vi.fn(async (..._args: unknown[]) => ({ ...receipt, status: 'VOIDED' })),
    trackShopFloor: vi.fn(),
    listReceiptsPage: vi.fn(async (_params?: unknown) => ({
      results: [receipt],
      count: 1,
      next: null,
      previous: null,
    })),
    getReceiptsSummary: vi.fn(async (_params?: unknown) => ({
      count: 1,
      collected: '0.00',
      chequesPending: '100.00',
      allocated: '0.00',
      advance: '100.00',
      excludedCount: 0,
    })),
    exportReceiptsCsv: vi.fn(async (_params?: unknown) => new Blob(['a,b'], { type: 'text/csv' })),
    fetchReceiptVoucher: vi.fn(async (..._args: unknown[]) => new Blob(['%PDF'], { type: 'application/pdf' })),
    createReceipt: vi.fn(async (..._args: unknown[]) => ({ ...receipt, id: 99 })),
    printBlob: vi.fn(),
    triggerBlobDownload: vi.fn(),
  };
});

vi.mock('@/lib/telemetry', () => ({
  trackShopFloor: (...args: unknown[]) => trackShopFloor(...args),
}));

vi.mock('@/utils/blob', () => ({
  printBlob: (...args: unknown[]) => printBlob(...args),
  triggerBlobDownload: (...args: unknown[]) => triggerBlobDownload(...args),
  openBlobInTab: vi.fn(),
}));

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 1, email: 'owner@x.test', fullName: 'Owner', role: 'OWNER', companyId: 9 },
  }),
}));

vi.mock('@/hooks/useSubscriptionGate', () => ({
  useSubscriptionGate: () => ({ writesBlocked: false, isLoading: false }),
}));

const listInvoices = vi.fn(async (_params?: unknown) => ({ results: [] as unknown[], count: 0, next: null, previous: null }));
const createAllocation = vi.fn(async (..._args: unknown[]) => ({}));
const unallocatePayment = vi.fn(async (..._args: unknown[]) => ({}));
const refundAdvance = vi.fn(async (..._args: unknown[]) => ({ id: 1, status: 'POSTED' }));
const editReceipt = vi.fn(async (..._args: unknown[]) => ({}));
const reassignReceiptCustomer = vi.fn(async (..._args: unknown[]) => ({}));
const correctClosedTill = vi.fn(async (..._args: unknown[]) => ({}));
const sendReceipt = vi.fn(async (..._args: unknown[]) => ({ mode: 'link', status: 'SENT' }));
const bulkAllocateReceipts = vi.fn(async (..._args: unknown[]) => [] as unknown[]);
const refundGatewayPayment = vi.fn(async (..._args: unknown[]) => ({}));
const getCompany = vi.fn(async () => ({ id: 9, chequeAllocationOnClearance: false, cash269stMode: 'warn' }));
const BANKS = [
  { id: 1, name: 'HDFC Current', accountType: 'CURRENT', isDefault: true, isActive: true },
  { id: 2, name: 'SBI Savings', accountType: 'SAVINGS', isDefault: false, isActive: true },
];
const listBankAccounts = vi.fn(async () => BANKS);

const CUSTOMERS = [
  { id: 10, name: 'Anil Store', phone: '9876543210', status: 'ACTIVE', outstanding: '500.00' },
  { id: 11, name: 'Counter Sale', phone: '', status: 'ACTIVE', outstanding: '0', isPosWalkIn: true },
];
const listCustomersPage = vi.fn(async (_params?: unknown) => ({
  results: CUSTOMERS,
  count: CUSTOMERS.length,
  next: null,
  previous: null,
}));

vi.mock('@/api/resources', () => ({
  listReceiptsPage: (...args: unknown[]) => listReceiptsPage(...args),
  getReceiptsSummary: (...args: unknown[]) => getReceiptsSummary(...args),
  exportReceiptsCsv: (...args: unknown[]) => exportReceiptsCsv(...args),
  fetchReceiptVoucher: (...args: unknown[]) => fetchReceiptVoucher(...args),
  createReceipt: (...args: unknown[]) => createReceipt(...args),
  listCustomersPage: (...args: unknown[]) => listCustomersPage(...args),
  listBankAccounts: () => listBankAccounts(),
  getCompany: () => getCompany(),
  listSalesInvoicesPage: (params?: unknown) => listInvoices(params),
  createAllocation: (...args: unknown[]) => createAllocation(...args),
  unallocatePayment: (...args: unknown[]) => unallocatePayment(...args),
  refundAdvance: (...args: unknown[]) => refundAdvance(...args),
  editReceipt: (...args: unknown[]) => editReceipt(...args),
  reassignReceiptCustomer: (...args: unknown[]) => reassignReceiptCustomer(...args),
  correctClosedTill: (...args: unknown[]) => correctClosedTill(...args),
  sendReceipt: (...args: unknown[]) => sendReceipt(...args),
  bulkAllocateReceipts: (...args: unknown[]) => bulkAllocateReceipts(...args),
  refundGatewayPayment: (...args: unknown[]) => refundGatewayPayment(...args),
  voidReceipt: (...args: unknown[]) => voidReceipt(...args),
  setReceiptChequeStatus: (...args: unknown[]) =>
    setReceiptChequeStatus(...(args as [number, string])),
}));

function wrap(ui: ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('ReceiptsPage cheque status', () => {
  it('clears a pending cheque from the row actions', async () => {
    wrap(<ReceiptsPage />);
    expect(await screen.findByText('RCT-0001')).toBeTruthy();
    expect(screen.getByText(/PENDING_CLEARANCE/)).toBeTruthy();
    await userEvent.click(screen.getByRole('button', { name: /mark cleared/i }));
    expect(setReceiptChequeStatus).toHaveBeenCalledWith(44, 'CLEARED');
  });

  it('shows distinct status chips for the receipt and its cheque', async () => {
    listReceiptsPage.mockResolvedValueOnce({
      results: [RECEIPT, VOIDED, { ...RECEIPT, id: 46, number: 'RCT-0003', chequeStatus: 'BOUNCED' }],
      count: 3,
      next: null,
      previous: null,
    });
    wrap(<ReceiptsPage />);
    expect(await screen.findByText('RCT-0002')).toBeTruthy();
    expect(screen.getByText('Voided')).toBeTruthy();
    expect(screen.getByText('Cheque pending')).toBeTruthy();
    expect(screen.getByText('Cheque bounced')).toBeTruthy();
    // A voided row offers no actions.
    const voidedRow = screen.getByText('RCT-0002').closest('tr') as HTMLElement;
    expect(within(voidedRow).queryByRole('button', { name: /^void$/i })).toBeNull();
  });

  it('pre-loads active customers when record receipt dialog opens without requiring 2 characters', async () => {
    wrap(<ReceiptsPage />);
    expect(await screen.findByText('RCT-0001')).toBeTruthy();
    const recordBtn = screen.getByRole('button', { name: /new receipt/i });
    await userEvent.click(recordBtn);
    expect(await screen.findByRole('dialog')).toBeTruthy();
    expect(listCustomersPage).toHaveBeenCalledWith(
      expect.objectContaining({ status: 'ACTIVE', pageSize: 50 }),
    );
  });
});

describe('ReceiptsPage voiding', () => {
  async function openVoid() {
    wrap(<ReceiptsPage />);
    expect(await screen.findByText('RCT-0001')).toBeTruthy();
    await userEvent.click(screen.getByRole('button', { name: /^void$/i }));
    return screen.findByRole('dialog');
  }

  it('will not void without a reason', async () => {
    const dialog = await openVoid();
    const confirm = within(dialog).getByRole('button', { name: /^void$/i }) as HTMLButtonElement;
    expect(confirm.disabled).toBe(true);
    await userEvent.type(within(dialog).getByLabelText(/reason for voiding/i), 'ab');
    expect(confirm.disabled).toBe(true);
    expect(within(dialog).getByText(/at least 3 characters/i)).toBeTruthy();
    expect(voidReceipt).not.toHaveBeenCalled();
  });

  it('sends the reason, tells the user the reversal posts today, and closes on success', async () => {
    const dialog = await openVoid();
    expect(within(dialog).getByText(/reversal is posted today/i)).toBeTruthy();
    await userEvent.type(within(dialog).getByLabelText(/reason for voiding/i), '  Duplicate   entry mistake ');
    await userEvent.click(within(dialog).getByRole('button', { name: /^void$/i }));
    expect(voidReceipt).toHaveBeenCalledWith(44, 'Duplicate entry mistake', { idempotencyKey: expect.any(String) });
    expect(await screen.findByText('Receipt voided')).toBeTruthy();
    expect(trackShopFloor).toHaveBeenCalledWith('document_voided', { feature: 'form' });
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  });

  it('keeps the dialog open, with the typed reason, when the void is refused', async () => {
    voidReceipt.mockRejectedValueOnce(new Error('This receipt is matched to a bank statement line.'));
    const dialog = await openVoid();
    await userEvent.type(within(dialog).getByLabelText(/reason for voiding/i), 'wrong customer');
    await userEvent.click(within(dialog).getByRole('button', { name: /^void$/i }));
    expect(await within(await screen.findByRole('dialog')).findByText(/matched to a bank statement line/)).toBeTruthy();
    const again = screen.getByRole('dialog');
    expect((within(again).getByLabelText(/reason for voiding/i) as HTMLInputElement).value).toBe('wrong customer');
    expect(screen.queryByText('Receipt voided')).toBeNull();
  });
});

describe('ReceiptsPage void of a bank-matched receipt', () => {
  it('names the bank line and links to reconciliation', async () => {
    const { AxiosError } = await import('axios');
    voidReceipt.mockRejectedValueOnce(
      new AxiosError('bad', 'ERR_BAD_REQUEST', undefined, undefined, {
        status: 400,
        statusText: 'Bad Request',
        headers: {},
        config: {} as never,
        data: {
          error: {
            code: 'receipt_bank_matched',
            message: 'This receipt is matched to a bank statement line. Open Bank reconciliation, unmatch line 77, then void this receipt.',
            details: { lineId: 77, statementId: 3 },
          },
        },
      }),
    );
    wrap(<ReceiptsPage />);
    await userEvent.click(await screen.findByRole('button', { name: /^void$/i }));
    const dialog = await screen.findByRole('dialog');
    await userEvent.type(within(dialog).getByLabelText(/reason for voiding/i), 'wrong customer');
    await userEvent.click(within(dialog).getByRole('button', { name: /^void$/i }));
    const link = await within(await screen.findByRole('dialog')).findByRole('link', { name: /open bank reconciliation/i });
    expect(link.getAttribute('href')).toBe('/payments/reconciliation?line=77');
  });
});

describe('ReceiptsPage voucher', () => {
  async function openVoucher(name = /open voucher RCT-0001/i) {
    wrap(<ReceiptsPage />);
    await userEvent.click(await screen.findByRole('button', { name }));
    return screen.findByRole('dialog');
  }

  it('opens from the receipt number, which names the customer for screen readers', async () => {
    const dialog = await openVoucher(/open voucher RCT-0001 for Ravi Traders/i);
    expect(within(dialog).getByText('Ravi Traders')).toBeTruthy();
    expect(within(dialog).getByText('2026-09-22')).toBeTruthy();
    expect(within(dialog).getByRole('button', { name: /print voucher/i })).toBeTruthy();
  });

  it('lists the invoices the receipt was applied to', async () => {
    listReceiptsPage.mockResolvedValueOnce({
      results: [
        {
          ...RECEIPT,
          amount: '150.00',
          allocated: '100.00',
          allocationLines: [{ salesInvoice: 7, invoiceNumber: 'INV-007', amount: '100.00' }],
        },
      ],
      count: 1,
      next: null,
      previous: null,
    });
    const dialog = await openVoucher();
    expect(within(dialog).getByText('INV-007')).toBeTruthy();
    expect(within(dialog).getByText('Advance')).toBeTruthy();
  });

  it('shows the void reason and who voided it, and no advance', async () => {
    listReceiptsPage.mockResolvedValueOnce({ results: [VOIDED], count: 1, next: null, previous: null });
    const dialog = await openVoucher(/open voucher RCT-0002/i);
    expect(within(dialog).getByText('entered twice')).toBeTruthy();
    expect(within(dialog).getByText('Owner')).toBeTruthy();
    expect(within(dialog).queryByText('Advance')).toBeNull();
  });

  it('prints the server PDF in the chosen layout', async () => {
    const dialog = await openVoucher();
    await userEvent.click(within(dialog).getByRole('button', { name: /print voucher/i }));
    await waitFor(() => expect(printBlob).toHaveBeenCalledTimes(1));
    expect(fetchReceiptVoucher).toHaveBeenCalledWith(44, 'A4', 'en');

    await userEvent.click(within(dialog).getByRole('combobox', { name: /paper/i }));
    await userEvent.click(await screen.findByRole('option', { name: /thermal/i }));
    await userEvent.click(within(dialog).getByRole('button', { name: /download pdf/i }));
    await waitFor(() => expect(triggerBlobDownload).toHaveBeenCalledTimes(1));
    expect(fetchReceiptVoucher).toHaveBeenLastCalledWith(44, 'THERMAL', 'en');
    expect(triggerBlobDownload.mock.calls[0][1]).toBe('receipt-RCT-0001.pdf');
  });

  it('prints in Hindi when that language is picked for the voucher', async () => {
    const dialog = await openVoucher();
    await userEvent.click(within(dialog).getByRole('combobox', { name: /language/i }));
    await userEvent.click(await screen.findByRole('option', { name: 'हिन्दी' }));
    await userEvent.click(within(dialog).getByRole('button', { name: /print voucher/i }));
    await waitFor(() => expect(fetchReceiptVoucher).toHaveBeenCalledWith(44, 'A4', 'hi'));
  });

  it('says so, and stays open, when the voucher cannot be prepared', async () => {
    fetchReceiptVoucher.mockRejectedValueOnce(new Error('Voucher service down'));
    const dialog = await openVoucher();
    await userEvent.click(within(dialog).getByRole('button', { name: /print voucher/i }));
    expect(await within(dialog).findByText(/Voucher service down/)).toBeTruthy();
    expect(printBlob).not.toHaveBeenCalled();
  });
});

describe('ReceiptsPage totals and filters', () => {
  it('shows server totals that cover every page, and what they leave out', async () => {
    getReceiptsSummary.mockResolvedValueOnce({
      count: 120,
      collected: '12000.00',
      chequesPending: '300.00',
      allocated: '9000.00',
      advance: '3300.00',
      excludedCount: 4,
    });
    wrap(<ReceiptsPage />);
    expect(await screen.findByText('₹12,000.00')).toBeTruthy();
    expect(screen.getByText('₹9,000.00')).toBeTruthy();
    expect(screen.getByText('₹3,300.00')).toBeTruthy();
    expect(screen.getByText('₹300.00')).toBeTruthy();
    expect(screen.getByText(/4 voided, refunded or bounced receipts are left out/i)).toBeTruthy();
  });

  it('hides the totals, not the list, when the totals fail', async () => {
    getReceiptsSummary.mockRejectedValueOnce(new Error('boom'));
    wrap(<ReceiptsPage />);
    expect(await screen.findByText('RCT-0001')).toBeTruthy();
    expect(await screen.findByText(/totals are unavailable/i)).toBeTruthy();
  });

  it('sends the same search, status and date filters to the list, the totals and the export', async () => {
    wrap(<ReceiptsPage />);
    expect(await screen.findByText('RCT-0001')).toBeTruthy();
    await userEvent.type(screen.getByLabelText(/search receipts/i), 'Ravi');
    const from = screen.getByLabelText(/from date/i);
    const to = screen.getByLabelText(/to date/i);
    await userEvent.type(from, '2026-09-01');
    await userEvent.type(to, '2026-09-30');

    const expected = expect.objectContaining({ q: 'Ravi', date_from: '2026-09-01', date_to: '2026-09-30' });
    await waitFor(() => expect(listReceiptsPage).toHaveBeenLastCalledWith(expect.objectContaining({ page: 1, pageSize: 50, q: 'Ravi', date_from: '2026-09-01', date_to: '2026-09-30' })));
    await waitFor(() => expect(getReceiptsSummary).toHaveBeenLastCalledWith(expected));

    await userEvent.click(screen.getByRole('button', { name: /export csv/i }));
    await waitFor(() => expect(exportReceiptsCsv).toHaveBeenCalledWith(expected));
    await waitFor(() => expect(triggerBlobDownload).toHaveBeenCalledWith(expect.any(Blob), 'customer-receipts.csv'));
    expect(await screen.findByText('Export downloaded')).toBeTruthy();
  });

  it('filters by status, and clears every filter at once', async () => {
    wrap(<ReceiptsPage />);
    expect(await screen.findByText('RCT-0001')).toBeTruthy();
    await userEvent.click(screen.getAllByRole('combobox', { name: /status/i })[0]);
    await userEvent.click(await screen.findByRole('option', { name: /voided/i }));
    await waitFor(() => expect(listReceiptsPage).toHaveBeenLastCalledWith(expect.objectContaining({ status: 'VOIDED' })));
    await userEvent.click(screen.getByRole('button', { name: /clear filters/i }));
    await waitFor(() =>
      expect(listReceiptsPage).toHaveBeenLastCalledWith(expect.objectContaining({ status: undefined, q: undefined })),
    );
  });

  it('holds the request and blocks export while the date range is back to front', async () => {
    wrap(<ReceiptsPage />);
    expect(await screen.findByText('RCT-0001')).toBeTruthy();
    await userEvent.type(screen.getByLabelText(/from date/i), '2026-09-30');
    await userEvent.type(screen.getByLabelText(/to date/i), '2026-09-01');
    expect(await screen.findByText(/start date must be on or before/i)).toBeTruthy();
    expect((screen.getByRole('button', { name: /export csv/i }) as HTMLButtonElement).disabled).toBe(true);
    const bad = listReceiptsPage.mock.calls.filter(
      ([params]) => (params as { date_from?: string; date_to?: string }).date_from === '2026-09-30' &&
        (params as { date_to?: string }).date_to === '2026-09-01',
    );
    expect(bad).toHaveLength(0);
  });
});

describe('ReceiptsPage recording a receipt', () => {
  async function openNew() {
    wrap(<ReceiptsPage />);
    expect(await screen.findByText('RCT-0001')).toBeTruthy();
    await userEvent.click(screen.getByRole('button', { name: /new receipt/i }));
    return screen.findByRole('dialog');
  }

  async function pickCustomer(dialog: HTMLElement, name: string) {
    const box = within(dialog).getByRole('combobox', { name: /customer/i });
    await userEvent.click(box);
    await userEvent.click(await screen.findByRole('option', { name: new RegExp(name, 'i') }));
  }

  const OPEN_BILL = {
    id: 5,
    number: 'INV-005',
    customer: 10,
    status: 'COMPLETED',
    balance: '100.00',
    invoiceDate: '2026-09-01',
  };

  it('lets a named customer leave an advance', async () => {
    const dialog = await openNew();
    await pickCustomer(dialog, 'Anil Store');
    await userEvent.type(within(dialog).getByLabelText(/^amount$/i), '250');
    await userEvent.click(within(dialog).getByRole('button', { name: /^save$/i }));
    await waitFor(() => expect(createReceipt).toHaveBeenCalledTimes(1));
    const payload = createReceipt.mock.calls[0][0] as Record<string, unknown>;
    expect(payload).toMatchObject({ customer: 10, amount: 250, mode: 'CASH' });
    expect(payload.salesInvoice).toBeUndefined();
    expect(payload.allocateAmount).toBeUndefined();
    expect(createAllocation).not.toHaveBeenCalled();
    expect(await screen.findByText('Receipt created')).toBeTruthy();
  });

  it('applies to one invoice in the same request as the receipt', async () => {
    listInvoices.mockResolvedValue({ results: [OPEN_BILL], count: 1, next: null, previous: null });
    const dialog = await openNew();
    await pickCustomer(dialog, 'Anil Store');
    await userEvent.type(within(dialog).getByLabelText(/^amount$/i), '100');
    await userEvent.click(within(dialog).getByRole('combobox', { name: /apply to specific invoice/i }));
    await userEvent.click(await screen.findByRole('option', { name: /INV-005/ }));
    await userEvent.click(within(dialog).getByRole('button', { name: /^save$/i }));
    await waitFor(() => expect(createReceipt).toHaveBeenCalledTimes(1));
    expect(createReceipt.mock.calls[0][0]).toMatchObject({ customer: 10, amount: 100, salesInvoice: 5, allocateAmount: 100 });
    // The second round trip is gone: a failed allocation can no longer strand the receipt.
    expect(createAllocation).not.toHaveBeenCalled();
  });

  it('refuses an allocation larger than the bill before calling the server', async () => {
    listInvoices.mockResolvedValue({ results: [OPEN_BILL], count: 1, next: null, previous: null });
    const dialog = await openNew();
    await pickCustomer(dialog, 'Anil Store');
    await userEvent.type(within(dialog).getByLabelText(/^amount$/i), '500');
    await userEvent.click(within(dialog).getByRole('combobox', { name: /apply to specific invoice/i }));
    await userEvent.click(await screen.findByRole('option', { name: /INV-005/ }));
    const applied = within(dialog).getByLabelText(/amount applied/i);
    await userEvent.clear(applied);
    await userEvent.type(applied, '400');
    await userEvent.click(within(dialog).getByRole('button', { name: /^save$/i }));
    expect(await within(dialog).findByText(/Allocation must be between 0.01 and 100.00/)).toBeTruthy();
    expect(createReceipt).not.toHaveBeenCalled();
  });

  it('tells the cashier a walk-in customer cannot keep an advance, and blocks it', async () => {
    const dialog = await openNew();
    await pickCustomer(dialog, 'Counter Sale');
    expect(within(dialog).getByText(/walk-in customers cannot hold an advance/i)).toBeTruthy();
    await userEvent.type(within(dialog).getByLabelText(/^amount$/i), '100');
    await userEvent.click(within(dialog).getByRole('button', { name: /^save$/i }));
    expect(await within(dialog).findByText(/must be applied to invoices in full/i)).toBeTruthy();
    expect(createReceipt).not.toHaveBeenCalled();
  });

  it('blocks a part-applied walk-in payment, but sends a fully applied one', async () => {
    listInvoices.mockResolvedValue({
      results: [{ ...OPEN_BILL, id: 6, number: 'INV-006', customer: 11 }],
      count: 1,
      next: null,
      previous: null,
    });
    const dialog = await openNew();
    await pickCustomer(dialog, 'Counter Sale');
    await userEvent.type(within(dialog).getByLabelText(/^amount$/i), '100');
    await userEvent.click(within(dialog).getByRole('combobox', { name: /apply to specific invoice/i }));
    await userEvent.click(await screen.findByRole('option', { name: /INV-006/ }));
    const applied = within(dialog).getByLabelText(/amount applied/i);
    await userEvent.clear(applied);
    await userEvent.type(applied, '60');
    await userEvent.click(within(dialog).getByRole('button', { name: /^save$/i }));
    expect(await within(dialog).findByText(/must be applied to invoices in full/i)).toBeTruthy();
    expect(createReceipt).not.toHaveBeenCalled();

    await userEvent.clear(applied);
    await userEvent.type(applied, '100');
    await userEvent.click(within(dialog).getByRole('button', { name: /^save$/i }));
    await waitFor(() => expect(createReceipt).toHaveBeenCalledTimes(1));
    expect(createReceipt.mock.calls[0][0]).toMatchObject({ customer: 11, salesInvoice: 6, allocateAmount: 100 });
  });

  it('shows the server refusal inside the dialog and keeps what was typed', async () => {
    createReceipt.mockRejectedValueOnce(new Error('A walk-in customer payment must be applied in full.'));
    const dialog = await openNew();
    await pickCustomer(dialog, 'Anil Store');
    await userEvent.type(within(dialog).getByLabelText(/^amount$/i), '75');
    await userEvent.click(within(dialog).getByRole('button', { name: /^save$/i }));
    expect(await within(dialog).findByText(/applied in full/)).toBeTruthy();
    expect((within(dialog).getByLabelText(/^amount$/i) as HTMLInputElement).value).toBe('75');
  });

  it('rejects a future date and nudges on a backdated one', async () => {
    const dialog = await openNew();
    await pickCustomer(dialog, 'Anil Store');
    await userEvent.type(within(dialog).getByLabelText(/^amount$/i), '10');
    const date = within(dialog).getByLabelText(/^date$/i);
    await userEvent.clear(date);
    await userEvent.type(date, '2020-01-01');
    expect(within(dialog).getByText(/backdated receipt/i)).toBeTruthy();
    await userEvent.clear(date);
    await userEvent.type(date, '2999-01-01');
    expect(within(dialog).getAllByText(/cannot be in the future/i).length).toBeGreaterThan(0);
    await userEvent.click(within(dialog).getByRole('button', { name: /^save$/i }));
    expect(createReceipt).not.toHaveBeenCalled();
  });

  it('passes the server notices on to the cashier', async () => {
    createReceipt.mockResolvedValueOnce({
      ...RECEIPT,
      id: 100,
      utrWarning: null,
      warnings: ['GST period for this date is already complete.'],
    });
    const dialog = await openNew();
    await pickCustomer(dialog, 'Anil Store');
    await userEvent.type(within(dialog).getByLabelText(/^amount$/i), '10');
    await userEvent.click(within(dialog).getByRole('button', { name: /^save$/i }));
    expect(await screen.findByText(/period for this date is already complete/i)).toBeTruthy();
  });
});

describe('ReceiptsPage allocating an advance', () => {
  const OPEN = (id: number, number: string, balance: string) => ({
    id,
    number,
    customer: 3,
    status: 'COMPLETED',
    balance,
    invoiceDate: '2026-09-01',
  });

  function mount() {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
    const invalidate = vi.spyOn(qc, 'invalidateQueries');
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <ReceiptsPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    return { invalidate };
  }

  async function openAllocateDialog() {
    expect(await screen.findByText('RCT-0001')).toBeTruthy();
    await userEvent.click(screen.getByRole('button', { name: /^allocate$/i }));
    return screen.findByRole('dialog');
  }

  async function pickBill(dialog: HTMLElement, name: RegExp) {
    await userEvent.click(within(dialog).getByRole('combobox', { name: /search all open bills/i }));
    await userEvent.click(await screen.findByRole('option', { name }));
  }

  it('lists only that customer bills that still owe money, and asks the server for them', async () => {
    listInvoices.mockResolvedValue({
      results: [OPEN(1, 'INV-1', '60.00'), OPEN(2, 'INV-2', '0'), OPEN(3, 'INV-3', '250.00')],
      count: 3,
      next: null,
      previous: null,
    });
    mount();
    const dialog = await openAllocateDialog();
    await userEvent.click(within(dialog).getByRole('combobox', { name: /search all open bills/i }));
    expect(await screen.findByRole('option', { name: /INV-1/ })).toBeTruthy();
    expect(screen.getByRole('option', { name: /INV-3/ })).toBeTruthy();
    expect(screen.queryByRole('option', { name: /INV-2/ })).toBeNull();
    expect(listInvoices).toHaveBeenCalledWith(expect.objectContaining({ customer: 3, status: 'COMPLETED' }));
  });

  it('searches every open bill on the server, not just the first page', async () => {
    listInvoices.mockResolvedValue({ results: [OPEN(1, 'INV-1', '60.00')], count: 1, next: null, previous: null });
    mount();
    const dialog = await openAllocateDialog();
    await userEvent.type(within(dialog).getByRole('combobox', { name: /search all open bills/i }), 'INV-9');
    await waitFor(() => expect(listInvoices).toHaveBeenCalledWith(expect.objectContaining({ q: 'INV-9' })));
  });

  it('applies the amount you choose, then refreshes receipts, totals and open bills', async () => {
    listInvoices.mockResolvedValue({ results: [OPEN(1, 'INV-1', '60.00')], count: 1, next: null, previous: null });
    createAllocation.mockClear();
    const { invalidate } = mount();
    const dialog = await openAllocateDialog();
    await pickBill(dialog, /INV-1/);
    // It starts at the smaller of the advance and the bill, and can be changed.
    const amount = within(dialog).getByLabelText(/amount to apply/i) as HTMLInputElement;
    expect(amount.value).toBe('60');
    await userEvent.clear(amount);
    await userEvent.type(amount, '25');
    await userEvent.click(within(dialog).getByRole('button', { name: /^apply$/i }));

    await waitFor(() => expect(createAllocation).toHaveBeenCalledTimes(1));
    expect(createAllocation.mock.calls[0][0]).toEqual({ receipt: 44, salesInvoice: 1, amount: 25 });
    expect(createAllocation.mock.calls[0][1]).toEqual({ idempotencyKey: expect.any(String) });

    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    const keys = invalidate.mock.calls.map((call) => JSON.stringify((call[0] as { queryKey: unknown }).queryKey));
    expect(keys).toContain(JSON.stringify(['receipts']));
    expect(keys).toContain(JSON.stringify(['receipts-summary']));
    expect(keys).toContain(JSON.stringify(['sales-invoices-open']));
  });

  it('never offers more than the advance when the bill is larger', async () => {
    listInvoices.mockResolvedValue({ results: [OPEN(3, 'INV-3', '250.00')], count: 1, next: null, previous: null });
    createAllocation.mockClear();
    mount();
    const dialog = await openAllocateDialog();
    await pickBill(dialog, /INV-3/);
    const amount = within(dialog).getByLabelText(/amount to apply/i) as HTMLInputElement;
    expect(amount.value).toBe('100');
    await userEvent.clear(amount);
    await userEvent.type(amount, '150');
    expect((within(dialog).getByRole('button', { name: /^apply$/i }) as HTMLButtonElement).disabled).toBe(true);
    expect(createAllocation).not.toHaveBeenCalled();
  });

  it('keeps the dialog open and shows the problem when the allocation is refused', async () => {
    listInvoices.mockResolvedValue({ results: [OPEN(1, 'INV-1', '60.00')], count: 1, next: null, previous: null });
    createAllocation.mockRejectedValueOnce(new Error('Period is closed'));
    mount();
    const dialog = await openAllocateDialog();
    await pickBill(dialog, /INV-1/);
    await userEvent.click(within(dialog).getByRole('button', { name: /^apply$/i }));
    expect(await screen.findByText(/Period is closed/)).toBeTruthy();
    expect(screen.getByRole('dialog')).toBeTruthy();
  });

  it('takes an allocation off again only with a reason', async () => {
    listReceiptsPage.mockResolvedValue({
      results: [{
        ...RECEIPT,
        unallocated: '0',
        allocatable: '0',
        allocated: '100.00',
        allocationLines: [
          { salesInvoice: 7, invoiceNumber: 'INV-7', amount: '100.00', discountApplied: '0', tdsApplied: '0', allocationId: 77 },
        ],
      }],
      count: 1,
      next: null,
      previous: null,
    });
    mount();
    expect(await screen.findByText('RCT-0001')).toBeTruthy();
    await userEvent.click(screen.getByRole('button', { name: /actions RCT-0001/i }));
    await userEvent.click(await screen.findByRole('menuitem', { name: /^allocations$/i }));
    const dialog = await screen.findByRole('dialog');
    await userEvent.click(within(dialog).getByRole('button', { name: /^unallocate$/i }));
    const confirm = within(dialog).getAllByRole('button', { name: /^unallocate$/i }).pop() as HTMLButtonElement;
    expect(confirm.disabled).toBe(true);
    await userEvent.type(within(dialog).getByLabelText(/reason for removing/i), 'applied to the wrong bill');
    await userEvent.click(confirm);
    await waitFor(() => expect(unallocatePayment).toHaveBeenCalledWith(77, 'applied to the wrong bill'));
  });
});

describe('ReceiptsPage Phase 2 input rules', () => {
  async function openNew() {
    wrap(<ReceiptsPage />);
    expect(await screen.findByText('RCT-0001')).toBeTruthy();
    await userEvent.click(screen.getByRole('button', { name: /new receipt/i }));
    return screen.findByRole('dialog');
  }
  async function pickCustomer(dialog: HTMLElement, name: string) {
    await userEvent.click(within(dialog).getByRole('combobox', { name: /^customer/i }));
    await userEvent.click(await screen.findByRole('option', { name: new RegExp(name, 'i') }));
  }
  const BILL = { id: 5, number: 'INV-005', customer: 10, status: 'COMPLETED', balance: '100.00', invoiceDate: '2026-09-01' };

  it('does not offer CREDIT as a way of being paid', async () => {
    const dialog = await openNew();
    await userEvent.click(within(dialog).getByRole('combobox', { name: /payment mode/i }));
    const names = screen.getAllByRole('option').map((o) => o.textContent);
    expect(names).toEqual(expect.arrayContaining(['CASH', 'UPI', 'BANK', 'CARD', 'CHEQUE']));
    expect(names).not.toContain('CREDIT');
  });

  it('keeps CREDIT as a filter so old rows stay findable', async () => {
    wrap(<ReceiptsPage />);
    await screen.findByText('RCT-0001');
    await userEvent.click(screen.getByRole('combobox', { name: /^mode$/i }));
    expect(screen.getByRole('option', { name: 'CREDIT' })).toBeTruthy();
  });

  it('preselects the default bank for bank money, and never offers the cash box', async () => {
    const dialog = await openNew();
    await pickCustomer(dialog, 'Anil Store');
    await userEvent.type(within(dialog).getByLabelText(/^amount$/i), '40');
    await userEvent.click(within(dialog).getByRole('combobox', { name: /payment mode/i }));
    await userEvent.click(await screen.findByRole('option', { name: 'UPI' }));
    await userEvent.click(within(dialog).getByRole('button', { name: /^save$/i }));
    await waitFor(() => expect(createReceipt).toHaveBeenCalledTimes(1));
    expect(createReceipt.mock.calls[0][0]).toMatchObject({ mode: 'UPI', bankAccount: 1 });
  });

  it('refuses bank money with no bank account before calling the server', async () => {
    listBankAccounts.mockResolvedValueOnce([
      { id: 3, name: 'Cash', accountType: 'CASH_BOX', isDefault: true, isActive: true },
    ]);
    const dialog = await openNew();
    await pickCustomer(dialog, 'Anil Store');
    await userEvent.type(within(dialog).getByLabelText(/^amount$/i), '40');
    await userEvent.click(within(dialog).getByRole('combobox', { name: /payment mode/i }));
    await userEvent.click(await screen.findByRole('option', { name: 'UPI' }));
    expect(await within(dialog).findByText(/no bank account yet/i)).toBeTruthy();
    await userEvent.click(within(dialog).getByRole('button', { name: /^save$/i }));
    expect(await within(dialog).findByText(/choose the bank account/i)).toBeTruthy();
    expect(createReceipt).not.toHaveBeenCalled();
  });

  it('clears the chosen bill when the customer changes', async () => {
    listInvoices.mockResolvedValue({ results: [BILL], count: 1, next: null, previous: null });
    const dialog = await openNew();
    await pickCustomer(dialog, 'Anil Store');
    await userEvent.type(within(dialog).getByLabelText(/^amount$/i), '100');
    await userEvent.click(within(dialog).getByRole('combobox', { name: /apply to specific invoice/i }));
    await userEvent.click(await screen.findByRole('option', { name: /INV-005/ }));
    expect(within(dialog).getByLabelText(/amount applied/i)).toBeTruthy();
    await pickCustomer(dialog, 'Counter Sale');
    expect(within(dialog).queryByLabelText(/amount applied/i)).toBeNull();
    expect((within(dialog).getByRole('combobox', { name: /apply to specific invoice/i }) as HTMLInputElement).value).toBe('');
  });

  it('keeps the applied amount in step with the amount until it is edited by hand', async () => {
    listInvoices.mockResolvedValue({ results: [BILL], count: 1, next: null, previous: null });
    const dialog = await openNew();
    await pickCustomer(dialog, 'Anil Store');
    const amount = within(dialog).getByLabelText(/^amount$/i);
    await userEvent.type(amount, '60');
    await userEvent.click(within(dialog).getByRole('combobox', { name: /apply to specific invoice/i }));
    await userEvent.click(await screen.findByRole('option', { name: /INV-005/ }));
    const applied = within(dialog).getByLabelText(/amount applied/i) as HTMLInputElement;
    expect(applied.value).toBe('60');
    await userEvent.clear(amount);
    await userEvent.type(amount, '80');
    expect(applied.value).toBe('80');
    await userEvent.clear(applied);
    await userEvent.type(applied, '30');
    await userEvent.clear(amount);
    await userEvent.type(amount, '90');
    expect(applied.value).toBe('30');
  });

  it('resets the payment mode and details after a save', async () => {
    const dialog = await openNew();
    await pickCustomer(dialog, 'Anil Store');
    await userEvent.type(within(dialog).getByLabelText(/^amount$/i), '40');
    await userEvent.click(within(dialog).getByRole('combobox', { name: /payment mode/i }));
    await userEvent.click(await screen.findByRole('option', { name: 'UPI' }));
    await userEvent.type(within(dialog).getByLabelText(/utr/i), 'UTR12345');
    await userEvent.click(within(dialog).getByRole('button', { name: /^save$/i }));
    await waitFor(() => expect(createReceipt).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    await userEvent.click(screen.getByRole('button', { name: /new receipt/i }));
    const again = await screen.findByRole('dialog');
    expect(within(again).getByRole('combobox', { name: /payment mode/i }).textContent).toBe('CASH');
    expect(within(again).queryByLabelText(/utr/i)).toBeNull();
  });

  it('finds archived customers only when asked to', async () => {
    const dialog = await openNew();
    expect(listCustomersPage).toHaveBeenLastCalledWith(expect.objectContaining({ status: 'ACTIVE' }));
    await userEvent.click(within(dialog).getByLabelText(/show inactive customers/i));
    await waitFor(() =>
      expect((listCustomersPage.mock.calls.at(-1)?.[0] as Record<string, unknown>).status).toBeUndefined(),
    );
  });

  it('sends TDS and a settlement discount, and refuses a discount with no bill to apply it to', async () => {
    listInvoices.mockResolvedValue({ results: [BILL], count: 1, next: null, previous: null });
    const dialog = await openNew();
    await pickCustomer(dialog, 'Anil Store');
    await userEvent.type(within(dialog).getByLabelText(/^amount$/i), '90');
    await userEvent.click(within(dialog).getByRole('button', { name: /more options/i }));
    await userEvent.type(await within(dialog).findByLabelText(/settlement discount/i), '5');
    await userEvent.click(within(dialog).getByRole('button', { name: /^save$/i }));
    expect(await within(dialog).findByText(/discount needs a bill/i)).toBeTruthy();
    expect(createReceipt).not.toHaveBeenCalled();

    await userEvent.click(within(dialog).getByRole('combobox', { name: /apply to specific invoice/i }));
    await userEvent.click(await screen.findByRole('option', { name: /INV-005/ }));
    await userEvent.type(within(dialog).getByLabelText(/tds deducted by customer/i), '5');
    await userEvent.click(within(dialog).getByRole('button', { name: /^save$/i }));
    await waitFor(() => expect(createReceipt).toHaveBeenCalledTimes(1));
    expect(createReceipt.mock.calls[0][0]).toMatchObject({ settlementDiscount: 5, tdsDeducted: 5, salesInvoice: 5 });
  });

  it('refuses a discount or TDS above the amount received', async () => {
    const dialog = await openNew();
    await pickCustomer(dialog, 'Anil Store');
    await userEvent.type(within(dialog).getByLabelText(/^amount$/i), '10');
    await userEvent.click(within(dialog).getByRole('button', { name: /more options/i }));
    await userEvent.type(await within(dialog).findByLabelText(/tds deducted by customer/i), '50');
    await userEvent.click(within(dialog).getByRole('button', { name: /^save$/i }));
    expect(await within(dialog).findByText(/tds cannot be more than the amount/i)).toBeTruthy();
    expect(createReceipt).not.toHaveBeenCalled();
  });

  it('warns about the s.269ST cash limit', async () => {
    const dialog = await openNew();
    await userEvent.type(within(dialog).getByLabelText(/^amount$/i), '250000');
    expect(await within(dialog).findByText(/269ST/)).toBeTruthy();
  });

  it('says a cheque is held as an advance when the company asks for that', async () => {
    getCompany.mockResolvedValue({ id: 9, chequeAllocationOnClearance: true, cash269stMode: 'warn' });
    listInvoices.mockResolvedValue({ results: [BILL], count: 1, next: null, previous: null });
    const dialog = await openNew();
    await pickCustomer(dialog, 'Anil Store');
    await userEvent.type(within(dialog).getByLabelText(/^amount$/i), '100');
    await userEvent.click(within(dialog).getByRole('combobox', { name: /payment mode/i }));
    await userEvent.click(await screen.findByRole('option', { name: 'CHEQUE' }));
    await userEvent.click(within(dialog).getByRole('combobox', { name: /apply to specific invoice/i }));
    await userEvent.click(await screen.findByRole('option', { name: /INV-005/ }));
    expect(await within(dialog).findByText(/held as advances until they clear/i)).toBeTruthy();
    getCompany.mockResolvedValue({ id: 9, chequeAllocationOnClearance: false, cash269stMode: 'warn' });
  });
});

describe('ReceiptsPage list controls', () => {
  it('sorts from the column header, sends the ordering, and marks the column for assistive tech', async () => {
    wrap(<ReceiptsPage />);
    await screen.findByText('RCT-0001');
    await userEvent.click(screen.getByRole('button', { name: /sort by amount/i }));
    await waitFor(() =>
      expect(listReceiptsPage.mock.calls.at(-1)?.[0]).toMatchObject({ ordering: '-amount' }),
    );
    const header = screen.getByRole('columnheader', { name: /amount/i });
    expect(header.getAttribute('aria-sort')).toBe('descending');
    await userEvent.click(screen.getByRole('button', { name: /sort by amount/i }));
    await waitFor(() =>
      expect((listReceiptsPage.mock.calls.at(-1)?.[0] as Record<string, unknown>).ordering).toBeUndefined(),
    );
  });

  it('changes the page size and jumps to a page', async () => {
    listReceiptsPage.mockResolvedValue({ results: [RECEIPT], count: 230, next: 'x', previous: null });
    wrap(<ReceiptsPage />);
    await screen.findByText('RCT-0001');
    await userEvent.click(screen.getByRole('combobox', { name: /rows per page/i }));
    await userEvent.click(await screen.findByRole('option', { name: '100' }));
    await waitFor(() => expect(listReceiptsPage.mock.calls.at(-1)?.[0]).toMatchObject({ pageSize: 100, page: 1 }));
    await userEvent.type(screen.getByLabelText(/go to page/i), '3');
    await userEvent.click(screen.getByRole('button', { name: /^go$/i }));
    await waitFor(() => expect(listReceiptsPage.mock.calls.at(-1)?.[0]).toMatchObject({ pageSize: 100, page: 3 }));
    listReceiptsPage.mockResolvedValue({ results: [RECEIPT], count: 1, next: null, previous: null });
  });

  it('filters by bank match and sends it with the list, the totals and the export', async () => {
    wrap(<ReceiptsPage />);
    await screen.findByText('RCT-0001');
    await userEvent.click(screen.getByRole('combobox', { name: /bank match/i }));
    await userEvent.click(await screen.findByRole('option', { name: /^matched$/i }));
    await waitFor(() => expect(listReceiptsPage.mock.calls.at(-1)?.[0]).toMatchObject({ reconciled: 'true' }));
    await waitFor(() => expect(getReceiptsSummary.mock.calls.at(-1)?.[0]).toMatchObject({ reconciled: 'true' }));
    await userEvent.click(screen.getByRole('button', { name: /export csv/i }));
    await waitFor(() => expect(exportReceiptsCsv).toHaveBeenCalledWith(expect.objectContaining({ reconciled: 'true' })));
  });

  it('shows a reconciled chip and the handed-back total', async () => {
    listReceiptsPage.mockResolvedValueOnce({
      results: [{ ...RECEIPT, reconciled: true }],
      count: 1,
      next: null,
      previous: null,
    });
    getReceiptsSummary.mockResolvedValueOnce({
      count: 1,
      collected: '60.00',
      chequesPending: '0.00',
      allocated: '0.00',
      advance: '60.00',
      refunded: '40.00',
      excludedCount: 0,
    });
    wrap(<ReceiptsPage />);
    expect(await screen.findByText('Reconciled')).toBeTruthy();
    expect(await screen.findByText('Handed back')).toBeTruthy();
  });

  it('puts a note about uncleared cheques under the totals', async () => {
    wrap(<ReceiptsPage />);
    expect(await screen.findByText(/include .*100.* in cheques that have not cleared/i)).toBeTruthy();
  });

  it('applies several advances to the oldest bills and shows one row per receipt', async () => {
    listReceiptsPage.mockResolvedValueOnce({
      results: [
        { ...RECEIPT, id: 50, number: 'RCT-0050', mode: 'CASH', chequeStatus: undefined },
        { ...RECEIPT, id: 51, number: 'RCT-0051', mode: 'CASH', chequeStatus: undefined },
      ],
      count: 2,
      next: null,
      previous: null,
    });
    bulkAllocateReceipts.mockResolvedValueOnce([
      { id: 50, number: 'RCT-0050', status: 'applied', allocated: '100.00', message: '' },
      { id: 51, number: 'RCT-0051', status: 'failed', allocated: '0.00', message: 'Period is closed' },
    ]);
    wrap(<ReceiptsPage />);
    await screen.findByText('RCT-0050');
    await userEvent.click(screen.getByRole('checkbox', { name: /select receipt RCT-0050/i }));
    await userEvent.click(screen.getByRole('checkbox', { name: /select receipt RCT-0051/i }));
    expect(screen.getByText(/2 selected/i)).toBeTruthy();
    await userEvent.click(screen.getByRole('button', { name: /apply to oldest bills/i }));
    const dialog = await screen.findByRole('dialog');
    await userEvent.click(within(dialog).getByRole('button', { name: /^apply$/i }));
    await waitFor(() => expect(bulkAllocateReceipts).toHaveBeenCalledTimes(1));
    expect(bulkAllocateReceipts.mock.calls[0][0]).toEqual([50, 51]);
    expect((bulkAllocateReceipts.mock.calls[0][1] as { idempotencyKey: string }).idempotencyKey).toBeTruthy();
    expect(await within(dialog).findByText(/1 applied, 0 skipped, 1 failed/i)).toBeTruthy();
    expect(within(dialog).getByText('Period is closed')).toBeTruthy();
  });
});

describe('ReceiptsPage corrections', () => {
  async function openMenu(item: RegExp) {
    wrap(<ReceiptsPage />);
    expect(await screen.findByText('RCT-0001')).toBeTruthy();
    await userEvent.click(screen.getByRole('button', { name: /actions RCT-0001/i }));
    await userEvent.click(await screen.findByRole('menuitem', { name: item }));
    return screen.findByRole('dialog');
  }

  it('refunds an advance with a reason, in the mode chosen', async () => {
    const dialog = await openMenu(/refund advance/i);
    const confirm = within(dialog).getByRole('button', { name: /^refund advance$/i }) as HTMLButtonElement;
    expect(confirm.disabled).toBe(true);
    await userEvent.clear(within(dialog).getByLabelText(/amount to refund/i));
    await userEvent.type(within(dialog).getByLabelText(/amount to refund/i), '40');
    await userEvent.type(within(dialog).getByLabelText(/^reason/i), 'customer asked for it back');
    await userEvent.click(confirm);
    await waitFor(() => expect(refundAdvance).toHaveBeenCalledTimes(1));
    expect(refundAdvance.mock.calls[0][0]).toBe(44);
    expect(refundAdvance.mock.calls[0][1]).toMatchObject({ amount: 40, mode: 'CASH', reason: 'customer asked for it back' });
    expect((refundAdvance.mock.calls[0][2] as { idempotencyKey: string }).idempotencyKey).toBeTruthy();
    expect(await screen.findByText('Advance refunded')).toBeTruthy();
  });

  it('will not refund more than is left', async () => {
    const dialog = await openMenu(/refund advance/i);
    const amount = within(dialog).getByLabelText(/amount to refund/i);
    await userEvent.clear(amount);
    await userEvent.type(amount, '150');
    await userEvent.type(within(dialog).getByLabelText(/^reason/i), 'customer asked for it back');
    expect((within(dialog).getByRole('button', { name: /^refund advance$/i }) as HTMLButtonElement).disabled).toBe(true);
  });

  it('edits only what changed', async () => {
    const dialog = await openMenu(/^edit$/i);
    expect(within(dialog).getByText(/cannot be changed. void the receipt/i)).toBeTruthy();
    const save = within(dialog).getByRole('button', { name: /^save$/i }) as HTMLButtonElement;
    expect(save.disabled).toBe(true);
    await userEvent.type(within(dialog).getByLabelText(/^notes$/i), 'checked with the bank');
    await userEvent.click(save);
    await waitFor(() => expect(editReceipt).toHaveBeenCalledWith(44, { notes: 'checked with the bank' }));
  });

  it('moves a walk-in receipt to the customer who paid', async () => {
    listReceiptsPage.mockResolvedValueOnce({
      results: [{ ...RECEIPT, customerIsWalkIn: true, mode: 'CASH', chequeStatus: undefined }],
      count: 1,
      next: null,
      previous: null,
    });
    const dialog = await openMenu(/move to customer/i);
    await userEvent.click(within(dialog).getByRole('combobox', { name: /customer/i }));
    await userEvent.click(await screen.findByRole('option', { name: /Anil Store/ }));
    await userEvent.type(within(dialog).getByLabelText(/^reason/i), 'paid by Anil');
    await userEvent.click(within(dialog).getByRole('button', { name: /move to customer/i }));
    await waitFor(() => expect(reassignReceiptCustomer).toHaveBeenCalledWith(44, { customer: 10, reason: 'paid by Anil' }));
  });

  it('corrects a closed till for a manager, with a reason', async () => {
    listReceiptsPage.mockResolvedValueOnce({
      results: [{ ...RECEIPT, mode: 'CASH', chequeStatus: undefined, shift: 12 }],
      count: 1,
      next: null,
      previous: null,
    });
    const dialog = await openMenu(/correct closed till/i);
    expect(within(dialog).getByText(/counted in the till of 2026-09-22/i)).toBeTruthy();
    await userEvent.type(within(dialog).getByLabelText(/reason for voiding/i), 'keyed against the wrong customer');
    await userEvent.click(within(dialog).getByRole('button', { name: /correct closed till/i }));
    await waitFor(() => expect(correctClosedTill).toHaveBeenCalledWith(44, 'keyed against the wrong customer'));
  });

  it('sends the voucher by WhatsApp and says so', async () => {
    const dialog = await openMenu(/^send$/i);
    await userEvent.click(within(dialog).getByRole('button', { name: /^send$/i }));
    await waitFor(() => expect(sendReceipt).toHaveBeenCalledWith(44, { channel: 'whatsapp' }));
  });

  it('offers a gateway refund to the owner on a gateway receipt', async () => {
    listReceiptsPage.mockResolvedValueOnce({
      results: [{ ...RECEIPT, mode: 'UPI', chequeStatus: undefined, source: 'GATEWAY', gatewayPayment: 31 }],
      count: 1,
      next: null,
      previous: null,
    });
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true);
    wrap(<ReceiptsPage />);
    await screen.findByText('RCT-0001');
    await userEvent.click(screen.getByRole('button', { name: /actions RCT-0001/i }));
    await userEvent.click(await screen.findByRole('menuitem', { name: /refund payment/i }));
    await waitFor(() => expect(refundGatewayPayment).toHaveBeenCalledWith(31));
    confirm.mockRestore();
  });
});

describe('ReceiptsPage accessibility', () => {
  // jsdom cannot compute colour contrast or layout, so those rules are left to the browser pass.
  async function violations() {
    const results = await axe.run(document.body, {
      rules: { 'color-contrast': { enabled: false }, region: { enabled: false } },
    });
    return results.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(' ')).join(' | ')}`);
  }

  it('has no violations on the list', async () => {
    wrap(<ReceiptsPage />);
    expect(await screen.findByText('RCT-0001')).toBeTruthy();
    expect(await screen.findByText('Collected')).toBeTruthy();
    expect(await violations()).toEqual([]);
  });

  it('has no violations in the voucher dialog, and focus returns to the receipt number on close', async () => {
    wrap(<ReceiptsPage />);
    const opener = await screen.findByRole('button', { name: /open voucher RCT-0001/i });
    await userEvent.click(opener);
    const dialog = await screen.findByRole('dialog');
    expect(await violations()).toEqual([]);
    await userEvent.click(within(dialog).getByRole('button', { name: /^close$/i }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    await waitFor(() => expect(document.activeElement).toBe(opener));
  });

  it('has no violations in the void dialog, which opens on the reason field', async () => {
    wrap(<ReceiptsPage />);
    await userEvent.click(await screen.findByRole('button', { name: /^void$/i }));
    const dialog = await screen.findByRole('dialog');
    expect(document.activeElement).toBe(within(dialog).getByLabelText(/reason for voiding/i));
    expect(await violations()).toEqual([]);
  });

  it('has no violations in the new receipt dialog', async () => {
    wrap(<ReceiptsPage />);
    await screen.findByText('RCT-0001');
    await userEvent.click(screen.getByRole('button', { name: /new receipt/i }));
    await screen.findByRole('dialog');
    expect(await violations()).toEqual([]);
  });

  it('has no violations in the refund, allocation and bulk dialogs', async () => {
    listReceiptsPage.mockResolvedValueOnce({
      results: [
        { ...RECEIPT, id: 60, number: 'RCT-0060', mode: 'CASH', chequeStatus: undefined },
        { ...RECEIPT, id: 61, number: 'RCT-0061', mode: 'CASH', chequeStatus: undefined },
      ],
      count: 2,
      next: null,
      previous: null,
    });
    wrap(<ReceiptsPage />);
    await screen.findByText('RCT-0060');
    await userEvent.click(screen.getAllByRole('button', { name: /actions RCT-0060/i })[0]);
    await userEvent.click(await screen.findByRole('menuitem', { name: /refund advance/i }));
    await screen.findByRole('dialog');
    expect(await violations()).toEqual([]);
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: /cancel/i }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());

    await userEvent.click(screen.getAllByRole('button', { name: /^allocate$/i })[0]);
    await screen.findByRole('dialog');
    expect(await violations()).toEqual([]);
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: /^close$/i }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());

    await userEvent.click(screen.getByRole('checkbox', { name: /select receipt RCT-0060/i }));
    await userEvent.click(screen.getByRole('checkbox', { name: /select receipt RCT-0061/i }));
    await userEvent.click(screen.getByRole('button', { name: /apply to oldest bills/i }));
    await screen.findByRole('dialog');
    expect(await violations()).toEqual([]);
  });
});


describe('ReceiptsPage offline', () => {
  beforeEach(async () => {
    const { listQueuedReceipts, removeQueuedReceipt } = await import('@/offline/receiptOutbox');
    for (const row of await listQueuedReceipts(9, 1)) await removeQueuedReceipt(row.id);
  });

  it('keeps a cash receipt on this device when there is no connection, and says so', async () => {
    const online = vi.spyOn(window.navigator, 'onLine', 'get').mockReturnValue(false);
    const { listQueuedReceipts, removeQueuedReceipt } = await import('@/offline/receiptOutbox');
    wrap(<ReceiptsPage />);
    await screen.findByText('RCT-0001');
    await userEvent.click(screen.getByRole('button', { name: /new receipt/i }));
    const dialog = await screen.findByRole('dialog');
    await userEvent.click(within(dialog).getByRole('combobox', { name: /^customer/i }));
    await userEvent.click(await screen.findByRole('option', { name: /Anil Store/ }));
    await userEvent.type(within(dialog).getByLabelText(/^amount$/i), '75');
    await userEvent.click(within(dialog).getByRole('button', { name: /^save$/i }));
    expect(await screen.findByText(/no connection\. this receipt is saved on this device/i)).toBeTruthy();
    expect(createReceipt).not.toHaveBeenCalled();
    const queued = await listQueuedReceipts(9, 1);
    expect(queued).toHaveLength(1);
    expect(queued[0].payload).toMatchObject({ customer: 10, amount: 75, mode: 'CASH' });
    expect(await screen.findByText('Waiting to send')).toBeTruthy();
    await removeQueuedReceipt(queued[0].id);
    online.mockRestore();
  });

  it('does not queue bank money offline: the server has to confirm the bank account', async () => {
    const online = vi.spyOn(window.navigator, 'onLine', 'get').mockReturnValue(false);
    createReceipt.mockRejectedValueOnce(Object.assign(new Error('Network Error'), { isAxiosError: true }));
    wrap(<ReceiptsPage />);
    await screen.findByText('RCT-0001');
    await userEvent.click(screen.getByRole('button', { name: /new receipt/i }));
    const dialog = await screen.findByRole('dialog');
    await userEvent.click(within(dialog).getByRole('combobox', { name: /^customer/i }));
    await userEvent.click(await screen.findByRole('option', { name: /Anil Store/ }));
    await userEvent.type(within(dialog).getByLabelText(/^amount$/i), '75');
    await userEvent.click(within(dialog).getByRole('combobox', { name: /payment mode/i }));
    await userEvent.click(await screen.findByRole('option', { name: 'UPI' }));
    await userEvent.click(within(dialog).getByRole('button', { name: /^save$/i }));
    await waitFor(() => expect(createReceipt).toHaveBeenCalledTimes(1));
    expect(screen.queryByText('Waiting to send')).toBeNull();
    online.mockRestore();
  });
});
