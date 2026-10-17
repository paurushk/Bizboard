import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { AxiosError } from 'axios';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { PurchaseReturnsPage } from '@/pages/purchases/PurchaseReturnsPage';
import { t } from '@/i18n';
import { registerGlobalConfirm } from '@/utils/confirmBridge';
import type { PurchaseReturn, ReturnableLine } from '@/types/domain';

const h = vi.hoisted(() => {
  const mkPurchase = (id: number, number: string, items: Array<Record<string, unknown>>) => ({
    id,
    number,
    supplier: 8,
    supplierName: 'Mega Suppliers',
    status: 'COMPLETED',
    invoiceDate: '2026-09-12',
    items,
  });
  const PURCHASE = mkPurchase(5, 'PUR-0005', [
    {
      id: 51,
      product: 6,
      productName: 'Phone',
      quantity: '3',
      unitPrice: '400',
      gstRate: '0',
      serialNumbers: ['P-1', 'P-2', 'P-3'],
    },
  ]);
  const OTHER = mkPurchase(9, 'PUR-0009', [
    { id: 91, product: 8, productName: 'Adapter', quantity: '2', unitPrice: '70', gstRate: '0' },
  ]);
  const BY_ID: Record<number, ReturnType<typeof mkPurchase>> = { 5: PURCHASE, 9: OTHER };
  const zero = {
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
    BY_ID,
    zero,
    createPurchaseReturn: vi.fn(async () => ({ id: 70, status: 'DRAFT', supplier: 8, purchaseInvoice: 5, returnDate: '2026-10-12', items: [], ...zero })),
    completePurchaseReturn: vi.fn(async () => ({ id: 70, status: 'COMPLETED', supplier: 8, purchaseInvoice: 5, returnDate: '2026-10-12', items: [], ...zero })),
    updatePurchaseReturn: vi.fn(async () => ({ id: 70, status: 'DRAFT', supplier: 8, purchaseInvoice: 5, returnDate: '2026-10-12', items: [], ...zero })),
    deletePurchaseReturn: vi.fn(async () => undefined),
    cancelPurchaseReturn: vi.fn(async (id: number) => ({ id, status: 'CANCELLED', supplier: 8, purchaseInvoice: 5, returnDate: '2026-10-12', items: [], ...zero })),
    getPurchaseReturn: vi.fn(),
    previewPurchaseReturnTotals: vi.fn(async () => ({
      lineCount: 1,
      units: 1,
      taxableTotal: 70,
      cgstTotal: 0,
      sgstTotal: 0,
      igstTotal: 0,
      cessTotal: 0,
      invoiceDiscount: 0,
      additionalCharges: 0,
      tcsAmount: 0,
      roundOff: 0,
      grandTotal: 70,
      fullyReturned: false,
    })),
    getPurchase: vi.fn(async (id: number) => BY_ID[id]),
    listPurchasesPage: vi.fn(async () => ({ results: [PURCHASE, OTHER], count: 2, next: null, previous: null })),
    listPurchaseReturnsPage: vi.fn(async () => ({ results: [] as PurchaseReturn[], count: 0, next: null, previous: null })),
    getPurchaseReturnableLines: vi.fn(async (id: number): Promise<ReturnableLine[]> =>
      (BY_ID[id].items as Array<Record<string, unknown>>).map((it) => ({
        sourceItem: it.id as number,
        product: it.product as number,
        productName: String(it.productName),
        sold: Number(it.quantity),
        returned: 0,
        creditedStandalone: 0,
        returnable: Number(it.quantity),
        returnedSerials: [],
      })),
    ),
  };
});

vi.mock('@/auth/AuthContext', () => ({ useAuth: () => ({ user: h.ctx.user }) }));
vi.mock('@/hooks/useSubscriptionGate', () => ({
  useSubscriptionGate: () => ({ writesBlocked: false, isLoading: false }),
}));
vi.mock('@/api/resources', () => ({
  listPurchaseReturnsPage: (...a: unknown[]) => h.listPurchaseReturnsPage(...(a as [])),
  listPurchasesPage: (...a: unknown[]) => h.listPurchasesPage(...(a as [])),
  listProducts: async () => [
    { id: 6, name: 'Phone', sku: 'PH', trackSerial: true },
    { id: 8, name: 'Adapter', sku: 'AD' },
  ],
  getPurchase: (...a: unknown[]) => h.getPurchase(...(a as [number])),
  getPurchaseReturn: (...a: unknown[]) => h.getPurchaseReturn(...a),
  previewPurchaseReturnTotals: (...a: unknown[]) => h.previewPurchaseReturnTotals(...(a as [])),
  getPurchaseReturnableLines: (...a: unknown[]) => h.getPurchaseReturnableLines(...(a as [number])),
  createPurchaseReturn: (...a: unknown[]) => h.createPurchaseReturn(...(a as [])),
  completePurchaseReturn: (...a: unknown[]) => h.completePurchaseReturn(...(a as [])),
  updatePurchaseReturn: (...a: unknown[]) => h.updatePurchaseReturn(...(a as [])),
  deletePurchaseReturn: (...a: unknown[]) => h.deletePurchaseReturn(...(a as [])),
  cancelPurchaseReturn: (...a: unknown[]) => h.cancelPurchaseReturn(...(a as [number])),
}));

function SearchProbe() {
  const location = useLocation();
  return <div data-testid="search">{location.search}</div>;
}

function mount(path: string, qc?: QueryClient) {
  const client = qc ?? new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <SearchProbe />
        <Routes>
          <Route path="/purchases/returns" element={<PurchaseReturnsPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const owner = { id: 1, email: 'owner@x.test', fullName: 'Owner', role: 'OWNER', companyId: 9 };
const buyerNoCancel = {
  id: 3,
  email: 'buyer@x.test',
  fullName: 'Buyer',
  role: 'PURCHASE_STAFF',
  companyId: 9,
  canCreatePurchases: true,
};

function row(over: Partial<PurchaseReturn> = {}): PurchaseReturn {
  return {
    id: 51,
    number: '',
    status: 'DRAFT',
    supplier: 8,
    supplierName: 'Mega Suppliers',
    purchaseInvoice: 5,
    purchaseInvoiceNumber: 'PUR-0005',
    returnDate: '2026-10-10',
    reason: 'Draft return',
    items: [],
    ...h.zero,
    grandTotal: 100,
    ...over,
  } as PurchaseReturn;
}

function completedRow(over: Partial<PurchaseReturn> = {}) {
  return row({
    id: 52,
    number: 'PRN-0052',
    status: 'COMPLETED',
    creditNoteId: 88,
    creditNoteNumber: 'PCN-0088',
    reason: 'Cracked',
    grandTotal: 200,
    ...over,
  });
}

const page = (results: PurchaseReturn[], next: string | null = null) => ({
  results,
  count: results.length,
  next,
  previous: null,
});

beforeEach(() => {
  h.ctx.user = owner;
  for (const fn of Object.values(h)) {
    const maybe = fn as { mockClear?: () => void };
    if (typeof maybe?.mockClear === 'function') maybe.mockClear();
  }
  h.listPurchaseReturnsPage.mockResolvedValue(page([]));
  h.getPurchaseReturn.mockReset();
  h.getPurchaseReturn.mockImplementation(async (id: number) => completedRow({ id }));
  h.previewPurchaseReturnTotals.mockReset();
  h.previewPurchaseReturnTotals.mockResolvedValue({
    lineCount: 1,
    units: 1,
    taxableTotal: 70,
    cgstTotal: 0,
    sgstTotal: 0,
    igstTotal: 0,
    cessTotal: 0,
    invoiceDiscount: 0,
    additionalCharges: 0,
    tcsAmount: 0,
    roundOff: 0,
    grandTotal: 70,
    fullyReturned: false,
  });
});

async function tickFirstLine() {
  fireEvent.click(await screen.findByRole('checkbox'));
}

async function pickPurchase(label: RegExp) {
  const user = userEvent.setup();
  for (let attempt = 0; attempt < 4; attempt += 1) {
    const combo = screen.getByRole('combobox', { name: /original purchase/i }) as HTMLInputElement;
    await user.click(combo);
    await user.click(await screen.findByRole('option', { name: label }));
    try {
      await waitFor(() => expect(combo.value).toMatch(label), { timeout: 2000 });
      return;
    } catch {
      /* retry: a click can be swallowed while the option list re-renders */
    }
  }
  throw new Error('Could not select the purchase');
}

describe('PurchaseReturnsPage inbound ?create=1', () => {
  it('opens the new-return dialog and removes the parameter from the address', async () => {
    mount('/purchases/returns?create=1');
    expect(await screen.findByRole('dialog', { name: t('phase1.newPurchaseReturn') })).toBeTruthy();
    await waitFor(() => expect(screen.getByTestId('search').textContent).toBe(''));
  });

  it('opens the return for the bill named in ?purchase= (a lot from Expiry alerts)', async () => {
    mount('/purchases/returns?purchase=5');
    expect(await screen.findByRole('dialog', { name: t('phase1.newPurchaseReturn') })).toBeTruthy();
    await waitFor(() => expect(h.getPurchase).toHaveBeenCalledWith(5));
    await waitFor(() => expect(screen.getByTestId('search').textContent).toBe(''));
    expect(await screen.findByDisplayValue(/PUR-0005/)).toBeTruthy();
  });

  it('does not open the dialog again after it is closed', async () => {
    mount('/purchases/returns?create=1');
    await screen.findByRole('dialog', { name: t('phase1.newPurchaseReturn') });
    await waitFor(() => expect(screen.getByTestId('search').textContent).toBe(''));
    await userEvent.click(screen.getByRole('button', { name: new RegExp(`^${t('common.cancel')}$`, 'i') }));
    await waitFor(() => expect(screen.queryByRole('dialog', { name: t('phase1.newPurchaseReturn') })).toBeNull());
    await new Promise((resolve) => setTimeout(resolve, 100));
    expect(screen.queryByRole('dialog', { name: t('phase1.newPurchaseReturn') })).toBeNull();
  });

  it('stays closed when the address has no create parameter', async () => {
    mount('/purchases/returns');
    await screen.findByText(t('nav.purchaseReturns'));
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('keeps other parameters in the address when it strips create', async () => {
    mount('/purchases/returns?create=1&q=abc');
    await screen.findByRole('dialog', { name: t('phase1.newPurchaseReturn') });
    await waitFor(() => expect(screen.getByTestId('search').textContent).toBe('?q=abc'));
  });
});

describe('PurchaseReturnsPage headroom and serials', () => {
  async function open(label: RegExp) {
    mount('/purchases/returns?create=1');
    await screen.findByRole('dialog', { name: t('phase1.newPurchaseReturn') });
    await pickPurchase(label);
  }

  it('caps the quantity at the server returnable figure', { timeout: 30000 }, async () => {
    h.getPurchaseReturnableLines.mockResolvedValueOnce([
      { sourceItem: 91, product: 8, productName: 'Adapter', sold: 2, returned: 1, creditedStandalone: 0, returnable: 1, returnedSerials: [] },
    ]);
    await open(/PUR-0009/);
    await tickFirstLine();
    expect((await screen.findByRole('spinbutton', { name: /qty/i })).getAttribute('max')).toBe('1');
    expect(h.getPurchaseReturnableLines).toHaveBeenCalledWith(9);
  });

  it('says so, and offers no lines, when returnable quantities cannot be loaded', { timeout: 30000 }, async () => {
    h.getPurchaseReturnableLines.mockRejectedValueOnce(new Error('Returnable quantities unavailable'));
    await open(/PUR-0009/);
    expect(await screen.findByText(/returnable quantities unavailable/i)).toBeTruthy();
    expect(screen.queryByRole('checkbox')).toBeNull();
  });

  it('picks the first received serial on tick, skips serials already returned, and sends quantity = picks', { timeout: 30000 }, async () => {
    h.getPurchaseReturnableLines.mockResolvedValueOnce([
      { sourceItem: 51, product: 6, productName: 'Phone', sold: 3, returned: 1, creditedStandalone: 0, returnable: 2, returnedSerials: ['P-2'] },
    ]);
    await open(/PUR-0005/);
    await tickFirstLine();
    expect(screen.queryByText('P-2')).toBeNull();
    fireEvent.click(await screen.findByText('P-3'));
    fireEvent.click(screen.getByRole('button', { name: /^complete$/i }));
    await waitFor(() => expect(h.createPurchaseReturn).toHaveBeenCalledTimes(1));
    const payload = h.createPurchaseReturn.mock.calls[0] as unknown as [{ items: Array<Record<string, unknown>> }];
    expect(payload[0].items[0]).toEqual(
      expect.objectContaining({ product: 6, quantity: 2, serialNumbers: ['P-1', 'P-3'] }),
    );
  });
});

describe('PurchaseReturnsPage credit note preview', () => {
  async function openAndTick() {
    mount('/purchases/returns?create=1');
    await screen.findByRole('dialog', { name: t('phase1.newPurchaseReturn') });
    await pickPurchase(/PUR-0009/);
    await tickFirstLine();
  }

  it('shows the exact credit-note total from the server', { timeout: 30000 }, async () => {
    await openAndTick();
    const box = await screen.findByTestId('return-preview');
    await waitFor(() => expect(within(box).getByText(/credit note total/i)).toBeTruthy(), { timeout: 3000 });
    expect(h.previewPurchaseReturnTotals).toHaveBeenCalledWith(
      expect.objectContaining({
        supplier: 8,
        purchaseInvoice: 9,
        items: [expect.objectContaining({ product: 8, quantity: 1 })],
      }),
    );
    expect(within(box).getByText(/exact figures/i)).toBeTruthy();
  });

  it('shows the server reason when the total cannot be computed', { timeout: 30000 }, async () => {
    h.previewPurchaseReturnTotals.mockRejectedValue(new Error('Return quantity exceeds remaining returnable quantity 1'));
    await openAndTick();
    expect(await screen.findByText(/total preview unavailable: return quantity exceeds/i, undefined, { timeout: 3000 })).toBeTruthy();
  });

  it('says it is being rate limited, in plain words, when the preview returns 429', { timeout: 30000 }, async () => {
    h.previewPurchaseReturnTotals.mockRejectedValue(
      new AxiosError('throttled', 'ERR_BAD_REQUEST', undefined, undefined, {
        status: 429,
        statusText: 'Too Many Requests',
        headers: {},
        config: {} as never,
        data: { error: { code: 'throttled', message: 'Request was throttled.' } },
      }),
    );
    await openAndTick();
    expect(await screen.findByText(/total preview unavailable/i, undefined, { timeout: 3000 })).toBeTruthy();
    expect(screen.getByText(/request was throttled/i)).toBeTruthy();
    // Complete still works: the preview is advisory.
    expect((screen.getByRole('button', { name: /^complete$/i }) as HTMLButtonElement).disabled).toBe(false);
  });
});

describe('PurchaseReturnsPage draft handling', () => {
  it('deletes the implicit draft and starts fresh when the bill is switched after a failed Complete', { timeout: 40000 }, async () => {
    h.completePurchaseReturn.mockRejectedValueOnce(new Error('Stock cannot be removed'));
    mount('/purchases/returns?create=1');
    await screen.findByRole('dialog', { name: t('phase1.newPurchaseReturn') });
    await pickPurchase(/PUR-0009/);
    await tickFirstLine();
    fireEvent.click(screen.getByRole('button', { name: /^complete$/i }));
    expect(await screen.findByText(/stock cannot be removed/i)).toBeTruthy();
    await pickPurchase(/PUR-0005/);
    await waitFor(() => expect(h.deletePurchaseReturn).toHaveBeenCalledWith(70));
    await tickFirstLine();
    fireEvent.click(screen.getByRole('button', { name: /^complete$/i }));
    await waitFor(() => expect(h.createPurchaseReturn).toHaveBeenCalledTimes(2));
    expect(h.updatePurchaseReturn).not.toHaveBeenCalled();
  });

  it('saves a draft without completing', { timeout: 30000 }, async () => {
    mount('/purchases/returns?create=1');
    await screen.findByRole('dialog', { name: t('phase1.newPurchaseReturn') });
    await pickPurchase(/PUR-0009/);
    await tickFirstLine();
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }));
    await waitFor(() => expect(h.createPurchaseReturn).toHaveBeenCalledTimes(1));
    expect(h.completePurchaseReturn).not.toHaveBeenCalled();
  });

  it('resumes a saved draft: hydrates lines from the server copy and locks the bill', async () => {
    h.listPurchaseReturnsPage.mockResolvedValue(page([row({ purchaseInvoice: 9 })]));
    h.getPurchaseReturn.mockResolvedValue(
      row({
        purchaseInvoice: 9,
        reason: 'Wrong colour',
        items: [{ product: 8, quantity: '1', condition: 'DAMAGED' }] as never,
      }),
    );
    mount('/purchases/returns');
    fireEvent.click(await screen.findByRole('button', { name: /^edit$/i }));
    expect(await screen.findByRole('dialog', { name: t('phase1.editPurchaseReturnDraft') })).toBeTruthy();
    expect(await screen.findByDisplayValue('Wrong colour')).toBeTruthy();
    expect(((await screen.findByRole('checkbox')) as HTMLInputElement).checked).toBe(true);
    expect((screen.getByRole('combobox', { name: /original purchase/i }) as HTMLInputElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }));
    await waitFor(() =>
      expect(h.updatePurchaseReturn).toHaveBeenCalledWith(51, expect.objectContaining({ reason: 'Wrong colour' })),
    );
  });
});

describe('PurchaseReturnsPage rows, detail and cache sync', () => {
  it('shows lifecycle actions, completes a draft, deletes a draft and cancels a completed return', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const spy = vi.spyOn(qc, 'invalidateQueries');
    h.listPurchaseReturnsPage.mockResolvedValue(page([row(), completedRow()]));
    mount('/purchases/returns', qc);
    expect(await screen.findByText('PRN-0052')).toBeTruthy();
    expect(screen.getByText('PCN-0088')).toBeTruthy();

    // WP-12: completing a draft return from the list asks first (it takes the quantity out of stock).
    const ask = vi.fn().mockResolvedValue(true);
    registerGlobalConfirm(ask);
    fireEvent.click(screen.getByRole('button', { name: /^complete$/i }));
    await waitFor(() => expect(h.completePurchaseReturn).toHaveBeenCalledWith(51, expect.any(Object)));
    expect(ask).toHaveBeenCalledTimes(1);
    expect(ask.mock.calls[0][0][0]).toMatch(/leaves stock/i);
    registerGlobalConfirm(null);

    fireEvent.click(screen.getByRole('button', { name: /^delete$/i }));
    const del = await screen.findByRole('dialog', { name: /^delete$/i });
    fireEvent.click(within(del).getByRole('button', { name: /^delete$/i }));
    await waitFor(() => expect(h.deletePurchaseReturn).toHaveBeenCalledWith(51));
    await waitFor(() => expect(screen.queryByRole('dialog', { name: /^delete$/i })).toBeNull());

    fireEvent.click(await screen.findByRole('button', { name: /cancel return/i }));
    const cancel = await screen.findByRole('dialog', { name: /cancel document/i });
    spy.mockClear();
    fireEvent.click(within(cancel).getByRole('button', { name: /cancel return/i }));
    await waitFor(() => expect(h.cancelPurchaseReturn).toHaveBeenCalledWith(52));
    await waitFor(() => {
      const seen = new Set(spy.mock.calls.map((c) => ((c[0] as { queryKey?: unknown[] })?.queryKey ?? [])[0]));
      for (const key of ['purchase-returns', 'purchase-credit-notes', 'purchases', 'products', 'stock-balance']) {
        expect(seen.has(key)).toBe(true);
      }
    });
  });

  it('does not complete a draft return when the confirmation is declined', async () => {
    h.listPurchaseReturnsPage.mockResolvedValue(page([row()]));
    registerGlobalConfirm(vi.fn().mockResolvedValue(false));
    mount('/purchases/returns');
    const complete = await screen.findByRole('button', { name: /^complete$/i });
    h.completePurchaseReturn.mockClear();
    fireEvent.click(complete);
    await new Promise((r) => setTimeout(r, 50));
    expect(h.completePurchaseReturn).not.toHaveBeenCalled();
    registerGlobalConfirm(null);
  });

  it('hides Cancel return from someone without the cancel permission', async () => {
    h.ctx.user = buyerNoCancel;
    h.listPurchaseReturnsPage.mockResolvedValue(page([completedRow()]));
    mount('/purchases/returns');
    await screen.findByText('PRN-0052');
    expect(screen.queryByRole('button', { name: /cancel return/i })).toBeNull();
  });

  it('shows discount %, GST % and the tax breakdown in the detail dialog', async () => {
    h.listPurchaseReturnsPage.mockResolvedValue(
      page([
        completedRow({
          cgstTotal: 9,
          sgstTotal: 9,
          roundOff: 0.4,
          items: [
            { id: 1, product: 6, productName: 'Phone', quantity: '2', unitPrice: '100', discountPercent: '10', gstRate: '18', lineTotal: '212.40', condition: 'SELLABLE' },
          ] as never,
        }),
      ]),
    );
    mount('/purchases/returns');
    fireEvent.click(await screen.findByRole('button', { name: /^view$/i }));
    const dialog = await screen.findByRole('dialog', { name: /PRN-0052/ });
    expect(within(dialog).getByText('Disc %')).toBeTruthy();
    expect(within(dialog).getByText('GST %')).toBeTruthy();
    const totals = within(dialog).getByTestId('return-detail-totals');
    expect(within(totals).getByText(/CGST/)).toBeTruthy();
    expect(within(totals).getByText(/round off/i)).toBeTruthy();
  });
});

describe('PurchaseReturnsPage detail refresh', () => {
  it('shows the return as it is on the server now, not the list row', async () => {
    h.listPurchaseReturnsPage.mockResolvedValue(page([completedRow({ reason: 'Old reason' })]));
    h.getPurchaseReturn.mockResolvedValue(completedRow({ reason: 'Fresh reason from the server' }));
    mount('/purchases/returns');
    fireEvent.click(await screen.findByRole('button', { name: /^view$/i }));
    const dialog = await screen.findByRole('dialog', { name: /PRN-0052/ });
    expect(await within(dialog).findByText(/fresh reason from the server/i)).toBeTruthy();
    expect(within(dialog).queryByText(/old reason/i)).toBeNull();
    expect(h.getPurchaseReturn).toHaveBeenCalledWith(52);
  });

  it('falls back to the list row when the fresh copy cannot be loaded', async () => {
    h.listPurchaseReturnsPage.mockResolvedValue(page([completedRow({ reason: 'Row reason' })]));
    h.getPurchaseReturn.mockRejectedValue(new Error('offline'));
    mount('/purchases/returns');
    fireEvent.click(await screen.findByRole('button', { name: /^view$/i }));
    const dialog = await screen.findByRole('dialog', { name: /PRN-0052/ });
    expect(await within(dialog).findByText(/row reason/i)).toBeTruthy();
  });
});

describe('PurchaseReturnsPage list filters', () => {
  it('sends search, status and date range to the server and can clear them', async () => {
    mount('/purchases/returns');
    await waitFor(() => expect(h.listPurchaseReturnsPage).toHaveBeenCalled());
    const user = userEvent.setup();
    await user.type(screen.getByLabelText(/^search$/i), 'cracked');
    await waitFor(() =>
      expect(h.listPurchaseReturnsPage).toHaveBeenLastCalledWith(expect.objectContaining({ q: 'cracked', page: 1 })),
    );
    fireEvent.change(screen.getByLabelText(/from date/i), { target: { value: '2026-10-01' } });
    fireEvent.change(screen.getByLabelText(/to date/i), { target: { value: '2026-10-31' } });
    await waitFor(() =>
      expect(h.listPurchaseReturnsPage).toHaveBeenLastCalledWith(
        expect.objectContaining({ q: 'cracked', date_from: '2026-10-01', date_to: '2026-10-31' }),
      ),
    );
    fireEvent.click(screen.getByRole('button', { name: /clear filters/i }));
    await waitFor(() => {
      const last = h.listPurchaseReturnsPage.mock.calls.at(-1)?.[0] as unknown as Record<string, unknown>;
      expect(last.q).toBeUndefined();
      expect(last.date_from).toBeUndefined();
    });
  });

  it('warns and does not query when From is after To', async () => {
    mount('/purchases/returns');
    await waitFor(() => expect(h.listPurchaseReturnsPage).toHaveBeenCalled());
    fireEvent.change(screen.getByLabelText(/to date/i), { target: { value: '2026-10-01' } });
    await waitFor(() =>
      expect(h.listPurchaseReturnsPage).toHaveBeenLastCalledWith(expect.objectContaining({ date_to: '2026-10-01' })),
    );
    h.listPurchaseReturnsPage.mockClear();
    fireEvent.change(screen.getByLabelText(/from date/i), { target: { value: '2026-10-20' } });
    expect(await screen.findByText(/cannot be after/i)).toBeTruthy();
    expect(h.listPurchaseReturnsPage).not.toHaveBeenCalled();
  });
});
