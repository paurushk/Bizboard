import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AxiosError } from 'axios';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { SalesReturnsPage } from '@/pages/sales/SalesReturnsPage';
import type { ReturnableLine, SalesInvoice, SalesReturn } from '@/types/domain';

const h = vi.hoisted(() => {
  const mkInvoice = (
    id: number,
    number: string,
    customerName: string,
    items: Array<Record<string, unknown>>,
    extra: Record<string, unknown> = {},
  ) =>
    ({
      id,
      number,
      status: 'COMPLETED',
      invoiceType: 'RETAIL',
      customer: 3,
      customerName,
      invoiceDate: '2026-09-12',
      grandTotal: '200.00',
      subtotal: '200.00',
      discountTotal: '20.00',
      taxableTotal: '180.00',
      cgstTotal: '0',
      sgstTotal: '0',
      igstTotal: '0',
      roundOff: '0',
      balance: '200.00',
      received: '0',
      items,
      ...extra,
    }) as unknown as SalesInvoice;

  const INVOICE_A = mkInvoice(7, 'INV-0007', 'Ravi Traders', [
    { id: 11, product: 4, productName: 'Widget', quantity: '2', unitPrice: '100', discountPercent: '10', gstRate: '0' },
  ]);
  const INVOICE_B = mkInvoice(8, 'INV-0008', 'Ravi Traders', [
    { id: 21, product: 5, productName: 'Gadget', quantity: '3', unitPrice: '50', discountPercent: '0', gstRate: '0' },
  ]);
  const INVOICE_SERIAL = mkInvoice(9, 'INV-0009', 'Ravi Traders', [
    {
      id: 31,
      product: 6,
      productName: 'Phone',
      quantity: '3',
      unitPrice: '500',
      discountPercent: '0',
      gstRate: '0',
      serialNumbers: ['SN-1', 'SN-2', 'SN-3'],
    },
  ]);
  const INVOICE_PLAIN_SERIAL = mkInvoice(10, 'INV-0010', 'Ravi Traders', [
    { id: 41, product: 6, productName: 'Phone', quantity: '3', unitPrice: '500', discountPercent: '0', gstRate: '0' },
  ]);
  const INVOICES: Record<number, SalesInvoice> = {
    7: INVOICE_A,
    8: INVOICE_B,
    9: INVOICE_SERIAL,
    10: INVOICE_PLAIN_SERIAL,
  };

  const zeroTotals = {
    subtotal: 0,
    discountTotal: 0,
    taxableTotal: 0,
    cgstTotal: 0,
    sgstTotal: 0,
    igstTotal: 0,
    roundOff: 0,
    grandTotal: 0,
  };

  return {
    ctx: { user: { id: 1, email: 'owner@x.test', fullName: 'Owner', role: 'OWNER', companyId: 9 } as Record<string, unknown> },
    INVOICE_A,
    INVOICE_B,
    INVOICES,
    zeroTotals,
    getSalesInvoice: vi.fn(async (id: number) => INVOICES[id]),
    listSalesInvoicesPage: vi.fn(async () => ({
      results: [INVOICE_A, INVOICE_B],
      count: 2,
      next: null,
      previous: null,
    })),
    listSalesReturns: vi.fn(async () => [] as SalesReturn[]),
    listSalesReturnsPage: vi.fn(async () => ({
      results: [] as SalesReturn[],
      count: 0,
      next: null,
      previous: null,
    })),
    getInvoiceReturnableLines: vi.fn(async (id: number): Promise<ReturnableLine[]> =>
      (INVOICES[id].items ?? []).map((it) => ({
        sourceItem: it.id as number,
        product: it.product,
        productName: String(it.productName),
        sold: Number(it.quantity),
        returned: 0,
        creditedStandalone: 0,
        returnable: Number(it.quantity),
        returnedSerials: [],
      })),
    ),
    getSalesReturn: vi.fn(),
    previewSalesReturnTotals: vi.fn(async () => ({
      lineCount: 1,
      units: 1,
      taxableTotal: 90,
      cgstTotal: 0,
      sgstTotal: 0,
      igstTotal: 0,
      cessTotal: 0,
      invoiceDiscount: 0,
      additionalCharges: 0,
      tcsAmount: 0,
      roundOff: 0,
      grandTotal: 90,
      fullyReturned: false,
    })),
    createSalesReturn: vi.fn(async () => ({
      id: 99,
      status: 'DRAFT',
      customer: 3,
      salesInvoice: 7,
      returnDate: '2026-10-12',
      items: [],
      ...zeroTotals,
    })),
    completeSalesReturn: vi.fn(async () => ({
      id: 99,
      number: 'SR-0099',
      status: 'COMPLETED',
      customer: 3,
      salesInvoice: 7,
      returnDate: '2026-10-12',
      items: [],
      ...zeroTotals,
      grandTotal: 180,
    })),
    updateSalesReturn: vi.fn(async () => ({ id: 99, status: 'DRAFT', customer: 3, salesInvoice: 7, items: [], ...zeroTotals })),
    deleteSalesReturn: vi.fn(async () => undefined),
    cancelSalesReturn: vi.fn(async (id: number) => ({
      id,
      status: 'CANCELLED',
      customer: 3,
      salesInvoice: 7,
      returnDate: '2026-10-12',
      items: [],
      ...zeroTotals,
    })),
  };
});

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ user: h.ctx.user }),
}));

vi.mock('@/hooks/useSubscriptionGate', () => ({
  useSubscriptionGate: () => ({ writesBlocked: false, isLoading: false }),
}));

vi.mock('@/api/resources', () => ({
  listSalesReturnsPage: (...args: unknown[]) => h.listSalesReturnsPage(...(args as [])),
  listSalesInvoicesPage: (...args: unknown[]) => h.listSalesInvoicesPage(...(args as [])),
  getSalesInvoice: (...args: unknown[]) => h.getSalesInvoice(...(args as [number])),
  getSalesReturn: (...args: unknown[]) => h.getSalesReturn(...args),
  getInvoiceReturnableLines: (...args: unknown[]) => h.getInvoiceReturnableLines(...(args as [number])),
  previewSalesReturnTotals: (...args: unknown[]) => h.previewSalesReturnTotals(...(args as [])),
  listProducts: async () => [
    { id: 4, name: 'Widget', sku: 'WID-1' },
    { id: 5, name: 'Gadget', sku: 'GAD-1' },
    { id: 6, name: 'Phone', sku: 'PHN-1', trackSerial: true },
  ],
  listSalesReturns: (...args: unknown[]) => h.listSalesReturns(...(args as [])),
  createSalesReturn: (...args: unknown[]) => h.createSalesReturn(...(args as [])),
  completeSalesReturn: (...args: unknown[]) => h.completeSalesReturn(...(args as [])),
  updateSalesReturn: (...args: unknown[]) => h.updateSalesReturn(...(args as [])),
  deleteSalesReturn: (...args: unknown[]) => h.deleteSalesReturn(...(args as [])),
  cancelSalesReturn: (...args: unknown[]) => h.cancelSalesReturn(...(args as [number])),
}));

function wrap(path: string, qc?: QueryClient) {
  const client = qc ?? new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/sales/returns" element={<SalesReturnsPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function guardError() {
  return new AxiosError('blocked', 'ERR_BAD_REQUEST', undefined, undefined, {
    status: 400,
    statusText: 'Bad Request',
    headers: {},
    config: {} as never,
    data: {
      error: {
        code: 'gst_guard_blocked',
        message: 'blocked',
        details: { blocking: [{ code: 'HSN_MISSING', message: 'HSN missing on a line' }] },
      },
    },
  });
}

function draftRow(overrides: Partial<SalesReturn> = {}): SalesReturn {
  return {
    id: 51,
    number: '',
    status: 'DRAFT',
    customer: 3,
    customerName: 'Ravi Traders',
    salesInvoice: 7,
    salesInvoiceNumber: 'INV-0007',
    returnDate: '2026-10-10',
    reason: 'Draft return',
    items: [],
    subtotal: 100,
    discountTotal: 0,
    taxableTotal: 100,
    cgstTotal: 0,
    sgstTotal: 0,
    igstTotal: 0,
    roundOff: 0,
    grandTotal: 100,
    ...overrides,
  } as SalesReturn;
}

function completedRow(overrides: Partial<SalesReturn> = {}): SalesReturn {
  return draftRow({
    id: 52,
    number: 'SR-0052',
    status: 'COMPLETED',
    creditNoteId: 88,
    creditNoteNumber: 'SCN-0088',
    returnDate: '2026-10-11',
    reason: 'Damaged box',
    grandTotal: 200,
    taxableTotal: 200,
    ...overrides,
  });
}

function pageOf(results: SalesReturn[], next: string | null = null) {
  return { results, count: results.length, next, previous: null };
}

const owner = { id: 1, email: 'owner@x.test', fullName: 'Owner', role: 'OWNER', companyId: 9 };
const staff = {
  id: 2,
  email: 'staff@x.test',
  fullName: 'Staff',
  role: 'SALES_STAFF',
  companyId: 9,
  canCreateSales: true,
};

beforeEach(() => {
  h.ctx.user = owner;
  for (const fn of [
    h.getSalesInvoice,
    h.listSalesReturns,
    h.listSalesReturnsPage,
    h.getInvoiceReturnableLines,
    h.getSalesReturn,
    h.previewSalesReturnTotals,
    h.createSalesReturn,
    h.completeSalesReturn,
    h.updateSalesReturn,
    h.deleteSalesReturn,
    h.cancelSalesReturn,
  ]) {
    fn.mockClear();
  }
  h.listSalesReturnsPage.mockResolvedValue(pageOf([]));
  h.listSalesReturns.mockResolvedValue([]);
  h.getSalesReturn.mockReset();
  h.getSalesReturn.mockImplementation(async (id: number) => completedRow({ id }));
  h.previewSalesReturnTotals.mockReset();
  h.previewSalesReturnTotals.mockResolvedValue({
    lineCount: 1,
    units: 1,
    taxableTotal: 90,
    cgstTotal: 0,
    sgstTotal: 0,
    igstTotal: 0,
    cessTotal: 0,
    invoiceDiscount: 0,
    additionalCharges: 0,
    tcsAmount: 0,
    roundOff: 0,
    grandTotal: 90,
    fullyReturned: false,
  });
});

async function tickFirstLine() {
  const checkbox = await screen.findByRole('checkbox');
  fireEvent.click(checkbox);
  return checkbox;
}

async function pickInvoiceFromList(label: RegExp) {
  const user = userEvent.setup();
  // The option list re-renders when the typed text changes, which can swallow a click;
  // confirm the selection landed and retry rather than assume it did.
  for (let attempt = 0; attempt < 4; attempt += 1) {
    const combo = screen.getByRole('combobox', { name: /original invoice/i }) as HTMLInputElement;
    await user.click(combo);
    await user.click(await screen.findByRole('option', { name: label }));
    try {
      await waitFor(() => expect(combo.value).toMatch(label), { timeout: 2000 });
      return;
    } catch {
      /* try again */
    }
  }
  throw new Error(`Could not select ${String(label)} in the invoice picker`);
}

describe('SalesReturnsPage headroom (SR-01, SRF-06)', () => {
  it('opens create, prefills the invoice, and asks the server for returnable lines', async () => {
    wrap('/sales/returns?create=1&invoice=7');
    expect(await screen.findByRole('dialog', { name: /new sales return/i })).toBeTruthy();
    expect(await screen.findByDisplayValue(/INV-0007/)).toBeTruthy();
    await waitFor(() => expect(h.getInvoiceReturnableLines).toHaveBeenCalledWith(7));
    expect(h.listSalesReturns).not.toHaveBeenCalled();
  });

  it('caps the quantity at the server returnable figure (standalone credit notes included)', async () => {
    h.getInvoiceReturnableLines.mockResolvedValueOnce([
      {
        sourceItem: 11,
        product: 4,
        productName: 'Widget',
        sold: 2,
        returned: 0,
        creditedStandalone: 1,
        returnable: 1,
        returnedSerials: [],
      },
    ]);
    wrap('/sales/returns?create=1&invoice=7');
    await screen.findByDisplayValue(/INV-0007/);
    await tickFirstLine();
    const qty = await screen.findByRole('spinbutton', { name: /qty/i });
    expect(qty.getAttribute('max')).toBe('1');
  });

  it('says so, and offers no lines, when the returnable quantities cannot be loaded', async () => {
    h.getInvoiceReturnableLines.mockRejectedValueOnce(new Error('Returnable quantities unavailable'));
    wrap('/sales/returns?create=1&invoice=7');
    expect(await screen.findByText(/returnable quantities unavailable/i)).toBeTruthy();
    expect(screen.queryByRole('checkbox')).toBeNull();
    expect(h.listSalesReturns).not.toHaveBeenCalled();
  });
});

describe('SalesReturnsPage payload (SR-02)', () => {
  it('sends sourceItem and discountPercent on Complete and then completes the draft', async () => {
    wrap('/sales/returns?create=1&invoice=7');
    await screen.findByDisplayValue(/INV-0007/);
    await tickFirstLine();
    fireEvent.click(screen.getByRole('button', { name: /^complete$/i }));
    await waitFor(() => expect(h.createSalesReturn).toHaveBeenCalledTimes(1));
    expect(h.createSalesReturn).toHaveBeenCalledWith(
      expect.objectContaining({
        customer: 3,
        salesInvoice: 7,
        items: [
          expect.objectContaining({
            product: 4,
            sourceItem: 11,
            quantity: 1,
            unitPrice: 100,
            discountPercent: 10,
            condition: 'SELLABLE',
          }),
        ],
      }),
      expect.any(Object),
    );
    await waitFor(() => expect(h.completeSalesReturn).toHaveBeenCalledWith(99, expect.any(Object)));
  });
});

describe('SalesReturnsPage serial returns (SRF-02)', () => {
  it('picks the first sold serial on tick, hides serials that already came back, and keeps qty = picks', async () => {
    h.getInvoiceReturnableLines.mockResolvedValueOnce([
      {
        sourceItem: 31,
        product: 6,
        productName: 'Phone',
        sold: 3,
        returned: 1,
        creditedStandalone: 0,
        returnable: 2,
        returnedSerials: ['SN-2'],
      },
    ]);
    wrap('/sales/returns?create=1&invoice=9');
    await screen.findByDisplayValue(/INV-0009/);
    await tickFirstLine();

    expect(screen.queryByText('SN-2')).toBeNull();
    const sn1 = await screen.findByText('SN-1');
    const sn3 = screen.getByText('SN-3');
    expect(sn1.closest('[aria-pressed]')?.getAttribute('aria-pressed')).toBe('true');
    expect(sn3.closest('[aria-pressed]')?.getAttribute('aria-pressed')).toBe('false');

    fireEvent.click(sn3);
    await waitFor(() => expect(sn3.closest('[aria-pressed]')?.getAttribute('aria-pressed')).toBe('true'));

    fireEvent.click(screen.getByRole('button', { name: /^complete$/i }));
    await waitFor(() => expect(h.createSalesReturn).toHaveBeenCalledTimes(1));
    const payload = h.createSalesReturn.mock.calls[0] as unknown as [{ items: Array<Record<string, unknown>> }];
    expect(payload[0].items[0]).toEqual(
      expect.objectContaining({ product: 6, sourceItem: 31, quantity: 2, serialNumbers: ['SN-1', 'SN-3'] }),
    );
  });

  it('stops offering serials once the returnable quantity is reached', async () => {
    h.getInvoiceReturnableLines.mockResolvedValueOnce([
      {
        sourceItem: 31,
        product: 6,
        productName: 'Phone',
        sold: 3,
        returned: 0,
        creditedStandalone: 2,
        returnable: 1,
        returnedSerials: [],
      },
    ]);
    wrap('/sales/returns?create=1&invoice=9');
    await screen.findByDisplayValue(/INV-0009/);
    await tickFirstLine();
    const sn2 = await screen.findByText('SN-2');
    expect(sn2.closest('.Mui-disabled')).not.toBeNull();
    fireEvent.click(sn2);
    expect(screen.getByText('SN-1').closest('[aria-pressed]')?.getAttribute('aria-pressed')).toBe('true');
    expect(sn2.closest('[aria-pressed]')?.getAttribute('aria-pressed')).toBe('false');
  });

  it('blocks Complete and Save while a free-text serial line has the wrong serial count', async () => {
    wrap('/sales/returns?create=1&invoice=10');
    await screen.findByDisplayValue(/INV-0010/);
    await tickFirstLine();
    expect(await screen.findByText(/enter the serial for phone/i)).toBeTruthy();
    expect((screen.getByRole('button', { name: /^complete$/i }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole('button', { name: /^save$/i }) as HTMLButtonElement).disabled).toBe(true);

    const serialInput = screen.getByRole('textbox', { name: '' });
    fireEvent.change(serialInput, { target: { value: 'SN-9' } });
    await waitFor(() =>
      expect((screen.getByRole('button', { name: /^complete$/i }) as HTMLButtonElement).disabled).toBe(false),
    );
  });
});

describe('SalesReturnsPage load races and loading state (SRF-03, SR-14)', () => {
  it('shows a loader, not the "nothing to return" warning, while lines load', async () => {
    let release: (rows: ReturnableLine[]) => void = () => {};
    h.getInvoiceReturnableLines.mockImplementationOnce(
      () => new Promise<ReturnableLine[]>((resolve) => { release = resolve; }),
    );
    wrap('/sales/returns?create=1&invoice=7');
    expect(await screen.findByTestId('return-lines-loading')).toBeTruthy();
    expect(screen.queryByText(/select at least one item to return/i)).toBeNull();
    release([]);
    await waitFor(() => expect(screen.queryByTestId('return-lines-loading')).toBeNull());
  });

  it('drops a slower response for an invoice the user already switched away from', { timeout: 30000 }, async () => {
    let releaseA: (rows: ReturnableLine[]) => void = () => {};
    h.getInvoiceReturnableLines.mockImplementationOnce(
      () => new Promise<ReturnableLine[]>((resolve) => { releaseA = resolve; }),
    );
    wrap('/sales/returns?create=1');
    await screen.findByRole('dialog', { name: /new sales return/i });
    await pickInvoiceFromList(/INV-0007/); // slow
    await pickInvoiceFromList(/INV-0008/); // fast
    await waitFor(() => expect(h.getInvoiceReturnableLines).toHaveBeenCalledTimes(2), { timeout: 15000 });
    expect(await screen.findByText('Gadget', undefined, { timeout: 15000 })).toBeTruthy();
    releaseA([
      { sourceItem: 11, product: 4, productName: 'Widget', sold: 2, returned: 0, creditedStandalone: 0, returnable: 2, returnedSerials: [] },
    ]);
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.queryByText('Widget')).toBeNull();
    expect(screen.getByText('Gadget')).toBeTruthy();
  });
});

describe('SalesReturnsPage draft handling (SR-07)', () => {
  it('deletes the implicit draft and starts a fresh one when the invoice is switched after a failed Complete', { timeout: 30000 }, async () => {
    h.completeSalesReturn.mockRejectedValueOnce(new Error('Stock cannot be restored'));
    wrap('/sales/returns?create=1&invoice=7');
    await screen.findByDisplayValue(/INV-0007/);
    await tickFirstLine();
    fireEvent.click(screen.getByRole('button', { name: /^complete$/i }));
    await waitFor(() => expect(h.completeSalesReturn).toHaveBeenCalledTimes(1));
    expect(await screen.findByText(/stock cannot be restored/i)).toBeTruthy();

    await pickInvoiceFromList(/INV-0008/);
    await waitFor(() => expect(h.deleteSalesReturn).toHaveBeenCalledWith(99));
    expect(await screen.findByText('Gadget')).toBeTruthy();
    await tickFirstLine();
    fireEvent.click(screen.getByRole('button', { name: /^complete$/i }));
    await waitFor(() => expect(h.createSalesReturn).toHaveBeenCalledTimes(2));
    expect(h.updateSalesReturn).not.toHaveBeenCalled();
  });

  it('retries a failed Complete by updating the same draft with a fresh complete key', async () => {
    h.completeSalesReturn.mockRejectedValueOnce(new Error('try again'));
    wrap('/sales/returns?create=1&invoice=7');
    await screen.findByDisplayValue(/INV-0007/);
    await tickFirstLine();
    fireEvent.click(screen.getByRole('button', { name: /^complete$/i }));
    await screen.findByText(/try again/i);
    fireEvent.click(screen.getByRole('button', { name: /^complete$/i }));
    await waitFor(() => expect(h.completeSalesReturn).toHaveBeenCalledTimes(2));
    expect(h.createSalesReturn).toHaveBeenCalledTimes(1);
    expect(h.updateSalesReturn).toHaveBeenCalledTimes(1);
    const keys = h.completeSalesReturn.mock.calls.map(
      (c) => (c as unknown as [number, { idempotencyKey: string }])[1].idempotencyKey,
    );
    expect(keys[0]).not.toBe(keys[1]);
  });

  it('discarding the dialog deletes an implicit draft but never a resumed one', async () => {
    h.completeSalesReturn.mockRejectedValueOnce(new Error('nope'));
    wrap('/sales/returns?create=1&invoice=7');
    await screen.findByDisplayValue(/INV-0007/);
    await tickFirstLine();
    fireEvent.click(screen.getByRole('button', { name: /^complete$/i }));
    await screen.findByText(/nope/i);
    fireEvent.click(screen.getByRole('button', { name: /^cancel$/i }));
    fireEvent.click(await screen.findByRole('button', { name: /^leave$/i }));
    await waitFor(() => expect(h.deleteSalesReturn).toHaveBeenCalledWith(99));
  });

  it('resumes a saved draft: hydrates lines from the server copy and locks the invoice', async () => {
    h.listSalesReturnsPage.mockResolvedValue(pageOf([draftRow()]));
    h.getSalesReturn.mockResolvedValue(
      draftRow({
        reason: 'Customer changed mind',
        items: [{ product: 4, sourceItem: 11, quantity: '1', condition: 'DAMAGED' }] as never,
      }),
    );
    wrap('/sales/returns');
    fireEvent.click(await screen.findByRole('button', { name: /^edit$/i }));
    expect(await screen.findByRole('dialog', { name: /edit sales return draft/i })).toBeTruthy();
    await waitFor(() => expect(h.getSalesReturn).toHaveBeenCalledWith(51));
    expect(await screen.findByDisplayValue('Customer changed mind')).toBeTruthy();
    const checkbox = (await screen.findByRole('checkbox')) as HTMLInputElement;
    expect(checkbox.checked).toBe(true);
    expect(((await screen.findByRole('spinbutton', { name: /qty/i })) as HTMLInputElement).value).toBe('1');
    expect((screen.getByRole('combobox', { name: /original invoice/i }) as HTMLInputElement).disabled).toBe(true);
    // The draft's own quantity is not subtracted from what can still be returned.
    expect((await screen.findByRole('spinbutton', { name: /qty/i })).getAttribute('max')).toBe('2');
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }));
    await waitFor(() => expect(h.updateSalesReturn).toHaveBeenCalledWith(51, expect.objectContaining({ reason: 'Customer changed mind' })));
    expect(h.deleteSalesReturn).not.toHaveBeenCalled();
  });
});

describe('SalesReturnsPage permissions (SR-08)', () => {
  it('lets staff save a draft but not complete', async () => {
    h.ctx.user = staff;
    wrap('/sales/returns?create=1&invoice=7');
    await screen.findByDisplayValue(/INV-0007/);
    expect(await screen.findByText(/save this return as a draft/i)).toBeTruthy();
    await tickFirstLine();
    expect((screen.getByRole('button', { name: /^complete$/i }) as HTMLButtonElement).disabled).toBe(true);
    const save = screen.getByRole('button', { name: /^save$/i }) as HTMLButtonElement;
    expect(save.disabled).toBe(false);
    fireEvent.click(save);
    await waitFor(() => expect(h.createSalesReturn).toHaveBeenCalledTimes(1));
    expect(h.completeSalesReturn).not.toHaveBeenCalled();
  });

  it('hides Complete, Cancel return and Delete from staff on list rows except draft edit/delete', async () => {
    h.ctx.user = staff;
    h.listSalesReturnsPage.mockResolvedValue(pageOf([draftRow(), completedRow()]));
    wrap('/sales/returns');
    await screen.findByText('SR-0052');
    expect(screen.queryByRole('button', { name: /cancel return/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /^complete$/i })).toBeNull();
    expect(screen.getByRole('button', { name: /^edit$/i })).toBeTruthy();
    expect(screen.getByRole('button', { name: /^delete$/i })).toBeTruthy();
  });
});

describe('SalesReturnsPage cache sync (SR-09)', () => {
  it('invalidates every dependent query after Complete and after Cancel', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const spy = vi.spyOn(qc, 'invalidateQueries');
    const keysSeen = () =>
      new Set(spy.mock.calls.map((c) => ((c[0] as { queryKey?: unknown[] })?.queryKey ?? [])[0]));
    const expected = [
      'sales-returns',
      'completed-sales',
      'sales-invoices',
      'sales-credit-notes',
      'products',
      'stock-balance',
      'customers',
    ];

    wrap('/sales/returns?create=1&invoice=7', qc);
    await screen.findByDisplayValue(/INV-0007/);
    await tickFirstLine();
    spy.mockClear();
    fireEvent.click(screen.getByRole('button', { name: /^complete$/i }));
    await waitFor(() => expect(h.completeSalesReturn).toHaveBeenCalled());
    await waitFor(() => {
      for (const key of expected) expect(keysSeen().has(key)).toBe(true);
    });
  });

  it('invalidates the same set when a completed return is cancelled', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const spy = vi.spyOn(qc, 'invalidateQueries');
    h.listSalesReturnsPage.mockResolvedValue(pageOf([completedRow()]));
    wrap('/sales/returns', qc);
    fireEvent.click(await screen.findByRole('button', { name: /cancel return/i }));
    const dialog = await screen.findByRole('dialog', { name: /cancel document/i });
    spy.mockClear();
    fireEvent.click(within(dialog).getByRole('button', { name: /cancel return/i }));
    await waitFor(() => expect(h.cancelSalesReturn).toHaveBeenCalledWith(52));
    await waitFor(() => {
      const seen = new Set(spy.mock.calls.map((c) => ((c[0] as { queryKey?: unknown[] })?.queryKey ?? [])[0]));
      for (const key of ['sales-returns', 'completed-sales', 'sales-invoices', 'sales-credit-notes', 'products', 'stock-balance', 'customers']) {
        expect(seen.has(key)).toBe(true);
      }
    });
  });
});

describe('SalesReturnsPage GST Guard (SRF-09)', () => {
  it('shows the blocking issues in the dialog and retries with the override reason', async () => {
    h.completeSalesReturn.mockRejectedValueOnce(guardError());
    wrap('/sales/returns?create=1&invoice=7');
    await screen.findByDisplayValue(/INV-0007/);
    await tickFirstLine();
    fireEvent.click(screen.getByRole('button', { name: /^complete$/i }));
    expect(await screen.findByText('HSN missing on a line')).toBeTruthy();
    const override = screen.getByRole('button', { name: /override and complete/i }) as HTMLButtonElement;
    expect(override.disabled).toBe(true);
    fireEvent.change(screen.getByLabelText(/reason for override/i), { target: { value: 'Customer is exempt' } });
    expect(override.disabled).toBe(false);
    fireEvent.click(override);
    await waitFor(() => expect(h.completeSalesReturn).toHaveBeenCalledTimes(2));
    expect(h.completeSalesReturn.mock.calls[1]).toEqual([
      99,
      expect.objectContaining({ gstGuardOverrideReason: 'Customer is exempt' }),
    ]);
  });

  it('shows issues without an override field to a user who cannot override', async () => {
    h.ctx.user = { ...owner, role: 'ACCOUNTANT', canCancelDocuments: true, canCreateSales: true };
    h.completeSalesReturn.mockRejectedValueOnce(guardError());
    wrap('/sales/returns?create=1&invoice=7');
    await screen.findByDisplayValue(/INV-0007/);
    await tickFirstLine();
    fireEvent.click(screen.getByRole('button', { name: /^complete$/i }));
    expect(await screen.findByText('HSN missing on a line')).toBeTruthy();
    expect(screen.queryByLabelText(/reason for override/i)).toBeNull();
    expect(screen.getByText(/only an owner or manager can override/i)).toBeTruthy();
  });

  it('handles a block when completing a draft straight from the list', async () => {
    h.listSalesReturnsPage.mockResolvedValue(pageOf([draftRow()]));
    h.completeSalesReturn.mockRejectedValueOnce(guardError());
    wrap('/sales/returns');
    fireEvent.click(await screen.findByRole('button', { name: /^complete$/i }));
    const dialog = await screen.findByRole('dialog', { name: /gst guard blocked/i });
    expect(within(dialog).getByText('HSN missing on a line')).toBeTruthy();
    fireEvent.change(within(dialog).getByLabelText(/reason for override/i), { target: { value: 'Approved by CA' } });
    fireEvent.click(within(dialog).getByRole('button', { name: /override and complete/i }));
    await waitFor(() => expect(h.completeSalesReturn).toHaveBeenCalledTimes(2));
    expect(h.completeSalesReturn.mock.calls[1]).toEqual([
      51,
      expect.objectContaining({ gstGuardOverrideReason: 'Approved by CA' }),
    ]);
  });
});

describe('SalesReturnsPage list filters (SRF-10)', () => {
  it('sends search, status and date range to the server and resets to page 1', async () => {
    wrap('/sales/returns');
    await waitFor(() => expect(h.listSalesReturnsPage).toHaveBeenCalled());
    const user = userEvent.setup();
    await user.type(screen.getByLabelText(/^search$/i), 'wobbly');
    await waitFor(() =>
      expect(h.listSalesReturnsPage).toHaveBeenLastCalledWith(expect.objectContaining({ q: 'wobbly', page: 1 })),
    );
    fireEvent.change(screen.getByLabelText(/from date/i), { target: { value: '2026-10-01' } });
    fireEvent.change(screen.getByLabelText(/to date/i), { target: { value: '2026-10-31' } });
    await waitFor(() =>
      expect(h.listSalesReturnsPage).toHaveBeenLastCalledWith(
        expect.objectContaining({ q: 'wobbly', date_from: '2026-10-01', date_to: '2026-10-31' }),
      ),
    );
    fireEvent.click(screen.getByRole('button', { name: /clear filters/i }));
    await waitFor(() => {
      const last = h.listSalesReturnsPage.mock.calls.at(-1)?.[0] as unknown as Record<string, unknown>;
      expect(last.q).toBeUndefined();
      expect(last.date_from).toBeUndefined();
    });
  });

  it('warns and does not query when From is after To', async () => {
    wrap('/sales/returns');
    await waitFor(() => expect(h.listSalesReturnsPage).toHaveBeenCalled());
    fireEvent.change(screen.getByLabelText(/to date/i), { target: { value: '2026-10-01' } });
    await waitFor(() =>
      expect(h.listSalesReturnsPage).toHaveBeenLastCalledWith(expect.objectContaining({ date_to: '2026-10-01' })),
    );
    h.listSalesReturnsPage.mockClear();
    fireEvent.change(screen.getByLabelText(/from date/i), { target: { value: '2026-10-20' } });
    expect(await screen.findByText(/cannot be after/i)).toBeTruthy();
    expect(h.listSalesReturnsPage).not.toHaveBeenCalled();
  });

  it('labels the status filter with localised status names', async () => {
    wrap('/sales/returns');
    const user = userEvent.setup();
    await user.click(screen.getByRole('combobox', { name: /status/i }));
    expect(await screen.findByRole('option', { name: 'Completed' })).toBeTruthy();
    expect(screen.getByRole('option', { name: 'Draft' })).toBeTruthy();
    expect(screen.getByRole('option', { name: 'Cancelled' })).toBeTruthy();
  });
});

describe('SalesReturnsPage totals preview (SRF-11)', () => {
  it('shows the exact credit-note total from the server once lines are chosen', async () => {
    wrap('/sales/returns?create=1&invoice=7');
    await screen.findByDisplayValue(/INV-0007/);
    await tickFirstLine();
    const box = await screen.findByTestId('return-preview');
    await waitFor(() => expect(within(box).getByText(/credit note total/i)).toBeTruthy(), { timeout: 3000 });
    expect(h.previewSalesReturnTotals).toHaveBeenCalledWith(
      expect.objectContaining({
        customer: 3,
        salesInvoice: 7,
        items: [expect.objectContaining({ product: 4, sourceItem: 11, quantity: 1 })],
      }),
    );
    expect(within(box).getByText(/exact figures/i)).toBeTruthy();
  });

  it('shows the server reason when the preview cannot be computed', async () => {
    h.previewSalesReturnTotals.mockRejectedValue(new Error('Credit note CN-1 already credited 1 unit'));
    wrap('/sales/returns?create=1&invoice=7');
    await screen.findByDisplayValue(/INV-0007/);
    await tickFirstLine();
    expect(await screen.findByText(/total preview unavailable: credit note cn-1/i, undefined, { timeout: 3000 })).toBeTruthy();
  });
});

describe('SalesReturnsPage preview rate limit', () => {
  it('says it is being rate limited, in plain words, and still lets Complete go ahead', async () => {
    h.previewSalesReturnTotals.mockRejectedValue(
      new AxiosError('throttled', 'ERR_BAD_REQUEST', undefined, undefined, {
        status: 429,
        statusText: 'Too Many Requests',
        headers: {},
        config: {} as never,
        data: { error: { code: 'throttled', message: 'Request was throttled.' } },
      }),
    );
    wrap('/sales/returns?create=1&invoice=7');
    await screen.findByDisplayValue(/INV-0007/);
    await tickFirstLine();
    expect(await screen.findByText(/total preview unavailable/i, undefined, { timeout: 3000 })).toBeTruthy();
    expect((screen.getByRole('button', { name: /^complete$/i }) as HTMLButtonElement).disabled).toBe(false);
  });
});

describe('SalesReturnsPage reason presets', () => {
  it('fills the reason, and "Defective" marks the selected lines Damaged', async () => {
    wrap('/sales/returns?create=1&invoice=7');
    await screen.findByDisplayValue(/INV-0007/);
    await tickFirstLine();
    fireEvent.click(screen.getByText('Wrong item'));
    expect((screen.getByLabelText(/^reason$/i) as HTMLInputElement).value).toBe('Wrong item');

    fireEvent.click(screen.getByText('Defective / damaged'));
    expect((screen.getByLabelText(/^reason$/i) as HTMLInputElement).value).toBe('Defective / damaged');
    fireEvent.click(screen.getByRole('button', { name: /^complete$/i }));
    await waitFor(() => expect(h.createSalesReturn).toHaveBeenCalledTimes(1));
    const call = h.createSalesReturn.mock.calls[0] as unknown as [{ reason: string; items: Array<Record<string, unknown>> }];
    expect(call[0].reason).toBe('Defective / damaged');
    expect(call[0].items[0]).toEqual(expect.objectContaining({ condition: 'DAMAGED' }));
  });

  it('does not change conditions for the other presets', async () => {
    wrap('/sales/returns?create=1&invoice=7');
    await screen.findByDisplayValue(/INV-0007/);
    await tickFirstLine();
    fireEvent.click(screen.getByText('Customer changed mind'));
    fireEvent.click(screen.getByRole('button', { name: /^complete$/i }));
    await waitFor(() => expect(h.createSalesReturn).toHaveBeenCalledTimes(1));
    const call = h.createSalesReturn.mock.calls[0] as unknown as [{ items: Array<Record<string, unknown>> }];
    expect(call[0].items[0]).toEqual(expect.objectContaining({ condition: 'SELLABLE' }));
  });
});

describe('SalesReturnsPage credit-becomes-advance notice (SRF-13)', () => {
  it('warns only when the credit is more than the amount still owed', async () => {
    h.INVOICE_A.balance = '50.00';
    try {
      wrap('/sales/returns?create=1&invoice=7');
      await screen.findByDisplayValue(/INV-0007/);
      await tickFirstLine();
      // The mocked preview credit is 90; only 50 is still owed, so 40 becomes advance.
      expect(await screen.findByText(/more than the amount still owed/i, undefined, { timeout: 3000 })).toBeTruthy();
    } finally {
      h.INVOICE_A.balance = '200.00';
    }
  });

  it('stays quiet when the credit fits inside the balance', async () => {
    wrap('/sales/returns?create=1&invoice=7');
    await screen.findByDisplayValue(/INV-0007/);
    await tickFirstLine();
    await within(await screen.findByTestId('return-preview')).findByText(/credit note total/i, undefined, { timeout: 3000 });
    expect(screen.queryByText(/more than the amount still owed/i)).toBeNull();
  });
});

describe('SalesReturnsPage row actions and detail (SR-03, SRF-04, SRF-12)', () => {
  it('renders lifecycle actions and cancels a completed return', async () => {
    h.listSalesReturnsPage.mockResolvedValue(pageOf([draftRow(), completedRow()]));
    wrap('/sales/returns');
    expect(await screen.findByText('SR-0052')).toBeTruthy();
    expect(screen.getByText('SCN-0088')).toBeTruthy();
    expect(screen.getByRole('button', { name: /^delete$/i })).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /cancel return/i }));
    const dialog = await screen.findByRole('dialog', { name: /cancel document/i });
    fireEvent.click(within(dialog).getByRole('button', { name: /cancel return/i }));
    await waitFor(() => expect(h.cancelSalesReturn).toHaveBeenCalledWith(52));
  });

  it('deletes a draft after confirmation', async () => {
    h.listSalesReturnsPage.mockResolvedValue(pageOf([draftRow()]));
    wrap('/sales/returns');
    fireEvent.click(await screen.findByRole('button', { name: /^delete$/i }));
    const dialog = await screen.findByRole('dialog', { name: /^delete$/i });
    fireEvent.click(within(dialog).getByRole('button', { name: /^delete$/i }));
    await waitFor(() => expect(h.deleteSalesReturn).toHaveBeenCalledWith(51));
  });

  it('shows discount %, GST % and the tax breakdown in the detail dialog', async () => {
    h.listSalesReturnsPage.mockResolvedValue(
      pageOf([
        completedRow({
          cgstTotal: 9,
          sgstTotal: 9,
          roundOff: 0.4,
          items: [
            {
              id: 1,
              product: 4,
              productName: 'Widget',
              quantity: '2',
              unitPrice: '100',
              discountPercent: '10',
              gstRate: '18',
              lineTotal: '212.40',
              condition: 'SELLABLE',
            },
          ] as never,
        }),
      ]),
    );
    wrap('/sales/returns');
    fireEvent.click(await screen.findByRole('button', { name: /^view$/i }));
    const dialog = await screen.findByRole('dialog', { name: /SR-0052/ });
    expect(within(dialog).getByText('Disc %')).toBeTruthy();
    expect(within(dialog).getByText('GST %')).toBeTruthy();
    const totals = within(dialog).getByTestId('return-detail-totals');
    expect(within(totals).getByText(/CGST/)).toBeTruthy();
    expect(within(totals).getByText(/SGST/)).toBeTruthy();
    expect(within(totals).getByText(/round off/i)).toBeTruthy();
  });
});

describe('SalesReturnsPage detail refresh', () => {
  it('shows the return as it is on the server now, not the list row', async () => {
    h.listSalesReturnsPage.mockResolvedValue(pageOf([completedRow({ reason: 'Old reason' })]));
    h.getSalesReturn.mockResolvedValue(completedRow({ reason: 'Fresh reason from the server' }));
    wrap('/sales/returns');
    fireEvent.click(await screen.findByRole('button', { name: /^view$/i }));
    const dialog = await screen.findByRole('dialog', { name: /SR-0052/ });
    expect(await within(dialog).findByText(/fresh reason from the server/i)).toBeTruthy();
    expect(within(dialog).queryByText(/old reason/i)).toBeNull();
    expect(h.getSalesReturn).toHaveBeenCalledWith(52);
  });

  it('falls back to the list row when the fresh copy cannot be loaded', async () => {
    h.listSalesReturnsPage.mockResolvedValue(pageOf([completedRow({ reason: 'Row reason' })]));
    h.getSalesReturn.mockRejectedValue(new Error('offline'));
    wrap('/sales/returns');
    fireEvent.click(await screen.findByRole('button', { name: /^view$/i }));
    const dialog = await screen.findByRole('dialog', { name: /SR-0052/ });
    expect(await within(dialog).findByText(/row reason/i)).toBeTruthy();
  });
});

describe('SalesReturnsPage inbound parameters', () => {
  function Probe() {
    const location = useLocation();
    return <div data-testid="search">{location.search}</div>;
  }
  function wrapWithProbe(path: string) {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    return render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={[path]}>
          <Probe />
          <Routes>
            <Route path="/sales/returns" element={<SalesReturnsPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
  }

  it('opens the dialog from ?create=1 alone, without looking up an invoice', async () => {
    wrapWithProbe('/sales/returns?create=1');
    expect(await screen.findByRole('dialog', { name: /new sales return/i })).toBeTruthy();
    expect(h.getSalesInvoice).not.toHaveBeenCalled();
  });

  it('removes the create and invoice parameters from the address once it has used them', async () => {
    wrapWithProbe('/sales/returns?create=1&invoice=7&q=abc');
    await screen.findByRole('dialog', { name: /new sales return/i });
    await waitFor(() => expect(screen.getByTestId('search').textContent).toBe('?q=abc'));
  });

  it('stays closed when the address has no parameters', async () => {
    wrapWithProbe('/sales/returns');
    await waitFor(() => expect(screen.queryByRole('progressbar')).toBeNull());
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('ignores an invoice id that is not a number', async () => {
    wrapWithProbe('/sales/returns?create=1&invoice=abc');
    await screen.findByRole('dialog', { name: /new sales return/i });
    expect(h.getSalesInvoice).not.toHaveBeenCalled();
  });
});
