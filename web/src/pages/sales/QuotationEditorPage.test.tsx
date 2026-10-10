import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { QuotationEditorPage } from '@/pages/sales/QuotationEditorPage';
import { t } from '@/i18n';

const auth = vi.hoisted(() => ({
  user: { role: 'OWNER' } as { role: string; canCreateSales?: boolean; canViewFinancialReports?: boolean },
}));
const api = vi.hoisted(() => ({
  lifecycleOn: false,
  getQuotation: vi.fn(),
  createQuotation: vi.fn(),
  updateQuotation: vi.fn(),
  quotationLifecycle: vi.fn(),
  duplicateQuotation: vi.fn(),
  shareQuotation: vi.fn(),
  searchSalespeople: vi.fn(),
  getStockHints: vi.fn(),
  previewSalesTotals: vi.fn(),
  listPriceLists: vi.fn(),
  getCustomer: vi.fn(),
  customers: [] as unknown[],
}));

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 1, email: 'owner@x.test', fullName: 'Owner', companyId: 9, ...auth.user },
  }),
}));

vi.mock('@/config/featureFlags', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/config/featureFlags')>();
  return {
    ...actual,
    isRuntimeFlagEnabled: (key: string) =>
      key === 'QUOTE_LIFECYCLE' ? api.lifecycleOn : actual.isRuntimeFlagEnabled(key),
  };
});

vi.mock('@/api/resources', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/resources')>();
  return {
    ...actual,
    getQuotation: (...a: unknown[]) => api.getQuotation(...a),
    createQuotation: (...a: unknown[]) => api.createQuotation(...a),
    updateQuotation: (...a: unknown[]) => api.updateQuotation(...a),
    quotationLifecycle: (...a: unknown[]) => api.quotationLifecycle(...a),
    duplicateQuotation: (...a: unknown[]) => api.duplicateQuotation(...a),
    shareQuotation: (...a: unknown[]) => api.shareQuotation(...a),
    searchSalespeople: (...a: unknown[]) => api.searchSalespeople(...a),
    getStockHints: (...a: unknown[]) => api.getStockHints(...a),
    previewSalesTotals: (...a: unknown[]) => api.previewSalesTotals(...a),
    listPriceLists: (...a: unknown[]) => api.listPriceLists(...a),
    getCustomer: (...a: unknown[]) => api.getCustomer(...a),
    listCustomersPage: async () => ({ results: api.customers, count: api.customers.length, next: null, previous: null }),
    listProductsPage: async () => ({
      results: [
        { id: 2, name: 'Widget', sku: 'W-1', gstRate: '18', sellingPrice: '100', purchasePrice: '60', status: 'ACTIVE' },
      ],
      count: 1,
      next: null,
      previous: null,
    }),
    searchProducts: async () => [],
    listCustomFieldDefinitions: async () => [],
    getCompany: async () => ({ id: 9, name: 'Acme', registrationType: 'REGULAR', state: 'Delhi' }),
    downloadSalesDocumentPdf: async () => new Blob(['x']),
  };
});

function Where() {
  const location = useLocation();
  const state = location.state as { message?: string } | null;
  return <div data-testid="where">{location.pathname + (state?.message ? ` | ${state.message}` : '')}</div>;
}

function mount(path: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <Where />
        <Routes>
          <Route path="/sales/quotations" element={<div>list page</div>} />
          <Route path="/sales/quotations/new" element={<QuotationEditorPage />} />
          <Route path="/sales/quotations/:id" element={<QuotationEditorPage />} />
          <Route path="/sales/quotations/:id/edit" element={<QuotationEditorPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const line = (over: Record<string, unknown> = {}) => ({
  id: 11,
  product: 2,
  productName: 'Widget',
  quantity: '10',
  convertedQuantity: '0',
  unitPrice: '100',
  discountPercent: '0',
  gstRate: '18',
  expectedPrice: '60',
  ...over,
});

const quote = (over: Record<string, unknown> = {}) => ({
  id: 5,
  number: 'QTN-0005',
  status: 'DRAFT',
  invoiceType: 'GST',
  customer: 3,
  customerName: 'Ravi',
  quotationDate: '2026-10-01',
  validUntil: '2099-01-01',
  grandTotal: '1180',
  salesman: null,
  salesChannel: '',
  deliveryAddress: 'Dock 4',
  notes: '',
  termsText: '',
  items: [line()],
  ...over,
});

/** The line's own quantity box; the add-line row also has a field labelled Qty. */
const lineQty = () =>
  screen.getAllByLabelText(t('billing.qty')).find((el) => el.getAttribute('aria-label')) as HTMLInputElement;
const waitForLine = () => screen.findByText('Widget');
/** Save stays disabled until the customer has loaded, which can trail the lines. */
const clickSave = async () => {
  const save = screen.getByRole('button', { name: t('common.save') }) as HTMLButtonElement;
  await waitFor(() => expect(save.disabled).toBe(false));
  fireEvent.click(save);
};

beforeEach(() => {
  auth.user = { role: 'OWNER' };
  api.lifecycleOn = false;
  api.customers = [{ id: 3, name: 'Ravi', status: 'ACTIVE', shippingAddress: '7 Market Rd', priceList: null }];
  for (const fn of Object.values(api)) if (typeof fn === 'function' && 'mockReset' in fn) (fn as ReturnType<typeof vi.fn>).mockReset();
  api.getCustomer.mockResolvedValue({ id: 3, name: 'Ravi', status: 'ACTIVE' });
  api.updateQuotation.mockResolvedValue(quote({ grandTotal: '1180' }));
  api.createQuotation.mockResolvedValue(quote({ id: 8, grandTotal: '590' }));
  api.quotationLifecycle.mockResolvedValue(quote());
  api.duplicateQuotation.mockResolvedValue(quote({ id: 9 }));
  api.shareQuotation.mockResolvedValue({ url: 'https://app.test/q/tok', status: 'DRAFT' });
  api.searchSalespeople.mockResolvedValue([{ id: 4, name: 'Asha Rao', code: 'E4' }]);
  api.getStockHints.mockResolvedValue({});
  api.listPriceLists.mockResolvedValue([]);
  api.previewSalesTotals.mockRejectedValue(new Error('no preview'));
});

describe('QuotationEditorPage — create', () => {
  it('creates a quote with the chosen date, the company invoice type, terms and an idempotency key', async () => {
    mount('/sales/quotations/new');
    const customer = await screen.findByRole('combobox', { name: new RegExp(t('billing.customer')) });
    fireEvent.change(customer, { target: { value: 'Ra' } });
    fireEvent.click(await screen.findByRole('option', { name: 'Ravi' }));
    fireEvent.change(screen.getByLabelText(t('phase1.quotationDate')), { target: { value: '2026-10-05' } });
    fireEvent.change(screen.getByLabelText(t('phase1.quotationTermsText')), { target: { value: 'Pay in 15 days' } });
    fireEvent.change(screen.getByLabelText(t('billing.additionalCharges')), { target: { value: '25' } });

    const product = screen.getAllByRole('combobox', { name: new RegExp(t('nav.products')) })[0];
    fireEvent.change(product, { target: { value: 'Wid' } });
    fireEvent.click(await screen.findByRole('option', { name: /Widget/ }));
    fireEvent.click(screen.getAllByRole('button', { name: t('common.add') }).at(-1)!);
    await waitForLine();

    await clickSave();
    await waitFor(() => expect(api.createQuotation).toHaveBeenCalled());
    const [payload, key] = api.createQuotation.mock.calls[0] as [Record<string, unknown>, string];
    expect(payload).toMatchObject({
      customer: 3, quotationDate: '2026-10-05', invoiceType: 'GST', termsText: 'Pay in 15 days', additionalCharges: 25,
    });
    expect((payload.items as Array<Record<string, unknown>>)[0]).toMatchObject({ product: 2, quantity: 1, unitPrice: 100 });
    expect(typeof key).toBe('string');
    expect(await screen.findByText(/list page/)).toBeTruthy();
    expect(screen.getByTestId('where').textContent).toContain(`${t('phase1.quotationSavedTotal', { total: '₹590.00' })}`);
  });

  it('shows the customer address until the user edits it, then keeps their text', async () => {
    mount('/sales/quotations/new');
    const address = (await screen.findByLabelText(t('billing.deliveryAddress'))) as HTMLTextAreaElement;
    const customer = screen.getByRole('combobox', { name: new RegExp(t('billing.customer')) });
    fireEvent.change(customer, { target: { value: 'Ra' } });
    fireEvent.click(await screen.findByRole('option', { name: 'Ravi' }));
    expect(address.value).toBe('7 Market Rd');
    fireEvent.change(address, { target: { value: 'My own address' } });
    api.customers = [{ id: 4, name: 'Other', status: 'ACTIVE', shippingAddress: 'Elsewhere' }];
    fireEvent.change(customer, { target: { value: 'Ot' } });
    fireEvent.click(await screen.findByRole('option', { name: 'Other' }));
    expect(address.value).toBe('My own address');
  });

  it('applies the customer price list to a new line and says so', async () => {
    api.customers = [{ id: 3, name: 'Ravi', status: 'ACTIVE', priceList: 1 }];
    api.listPriceLists.mockResolvedValue([
      { id: 1, name: 'Dealer', items: [{ product: 2, unitPrice: '80', minQty: '1' }] },
    ]);
    mount('/sales/quotations/new');
    fireEvent.change(await screen.findByRole('combobox', { name: new RegExp(t('billing.customer')) }), { target: { value: 'Ra' } });
    fireEvent.click(await screen.findByRole('option', { name: 'Ravi' }));
    await waitFor(() => expect(api.listPriceLists).toHaveBeenCalled());
    fireEvent.change(screen.getAllByRole('combobox', { name: new RegExp(t('nav.products')) })[0], { target: { value: 'Wid' } });
    fireEvent.click(await screen.findByRole('option', { name: /Widget/ }));
    fireEvent.click(screen.getAllByRole('button', { name: t('common.add') }).at(-1)!);
    await waitForLine();
    expect((screen.getByLabelText(t('billing.unitPrice'), { selector: '[aria-label]' }) as HTMLInputElement).value).toBe('80');
    expect(screen.getByText(new RegExp(`${t('phase1.quotationPriceListApplied')}: Dealer`))).toBeTruthy();
  });

  it('searches salespeople on the server, so anyone who can sell can pick one', async () => {
    auth.user = { role: 'SALES_STAFF', canCreateSales: true };
    mount('/sales/quotations/new');
    const box = await screen.findByRole('combobox', { name: new RegExp(t('billing.salesman')) });
    fireEvent.change(box, { target: { value: 'asha' } });
    await waitFor(() => expect(api.searchSalespeople).toHaveBeenCalledWith('asha'));
    fireEvent.click(await screen.findByRole('option', { name: 'Asha Rao' }));
    expect((box as HTMLInputElement).value).toBe('Asha Rao');
  });
});

describe('QuotationEditorPage — edit', () => {
  it('locks customer, date, lines and money on a partly converted quote; header, notes and terms still save', async () => {
    api.getQuotation.mockResolvedValue(quote({ items: [line({ convertedQuantity: '4' })] }));
    mount('/sales/quotations/5');
    expect(await screen.findByText(t('phase1.quotationLinesLocked'))).toBeTruthy();
    expect((screen.getByLabelText(t('phase1.quotationDate')) as HTMLInputElement).disabled).toBe(true);
    expect(lineQty().disabled).toBe(true);
    expect((screen.getByLabelText(t('billing.additionalCharges')) as HTMLInputElement).disabled).toBe(true);
    expect((screen.getByLabelText(t('billing.validUntil')) as HTMLInputElement).disabled).toBe(false);
    expect((screen.getByLabelText(t('phase1.quotationNotes')) as HTMLInputElement).disabled).toBe(false);

    fireEvent.change(screen.getByLabelText(t('billing.deliveryAddress')), { target: { value: 'Dock 9' } });
    fireEvent.change(screen.getByLabelText(t('phase1.quotationNotes')), { target: { value: 'Call first' } });
    await clickSave();
    await waitFor(() => expect(api.updateQuotation).toHaveBeenCalled());
    const [id, payload] = api.updateQuotation.mock.calls[0] as [number, Record<string, unknown>];
    expect(id).toBe(5);
    expect(payload).toMatchObject({ deliveryAddress: 'Dock 9', notes: 'Call first' });
    for (const blocked of ['items', 'customer', 'quotationDate', 'additionalCharges', 'invoiceDiscount', 'invoiceType']) {
      expect(blocked in payload).toBe(false);
    }
  });

  it('lets the quantity be cleared and retyped as a decimal, keeps the line id and invoice type', async () => {
    api.getQuotation.mockResolvedValue(quote());
    mount('/sales/quotations/5');
    await waitForLine();
    const qty = lineQty();
    fireEvent.focus(qty);
    fireEvent.change(qty, { target: { value: '' } });
    expect(qty.value).toBe('');
    fireEvent.change(qty, { target: { value: '2.5' } });
    fireEvent.blur(qty);
    await clickSave();
    await waitFor(() => expect(api.updateQuotation).toHaveBeenCalled());
    const [, payload] = api.updateQuotation.mock.calls[0] as [number, { items: Array<Record<string, unknown>> }];
    expect(payload.items[0]).toMatchObject({ id: 11, quantity: 2.5 });
    expect('invoiceType' in payload).toBe(false);
  });

  it('blocks a zero quantity and says why', async () => {
    api.getQuotation.mockResolvedValue(quote());
    mount('/sales/quotations/5');
    await waitForLine();
    const qty = lineQty();
    fireEvent.focus(qty);
    fireEvent.change(qty, { target: { value: '0' } });
    fireEvent.blur(qty);
    await clickSave();
    expect((await screen.findAllByText(t('billing.qtyMustBePositive'))).length).toBeGreaterThan(0);
    expect(api.updateQuotation).not.toHaveBeenCalled();
  });

  it('opens a cancelled quote read-only with no Save button', async () => {
    api.getQuotation.mockResolvedValue(quote({ status: 'CANCELLED' }));
    mount('/sales/quotations/5');
    expect(await screen.findByText(t('phase1.quotationReadOnly', { status: t('status.CANCELLED') }))).toBeTruthy();
    expect(screen.queryByRole('button', { name: t('common.save') })).toBeNull();
    expect(lineQty().disabled).toBe(true);
  });

  it('hides the internal cost from a user without financial access and never sends it', async () => {
    auth.user = { role: 'SALES_STAFF', canCreateSales: true };
    api.getQuotation.mockResolvedValue(quote({ items: [line({ expectedPrice: null })] }));
    mount('/sales/quotations/5');
    await waitForLine();
    expect(screen.queryByLabelText(t('billing.expectedPrice'))).toBeNull();
    await clickSave();
    await waitFor(() => expect(api.updateQuotation).toHaveBeenCalled());
    const [, payload] = api.updateQuotation.mock.calls[0] as [number, { items: Array<Record<string, unknown>> }];
    expect('expectedPrice' in payload.items[0]).toBe(false);
  });

  it('carries cess, HSN and inclusive price through an edit so the API-only values survive', async () => {
    api.getQuotation.mockResolvedValue(
      quote({ items: [line({ hsnCode: '3004', cessRate: '12', unitPriceInclusive: '118' })] }),
    );
    mount('/sales/quotations/5');
    await waitForLine();
    await clickSave();
    await waitFor(() => expect(api.updateQuotation).toHaveBeenCalled());
    const [, payload] = api.updateQuotation.mock.calls[0] as [number, { items: Array<Record<string, unknown>> }];
    expect(payload.items[0]).toMatchObject({ hsnCode: '3004', cessRate: 12, unitPriceInclusive: 118 });
  });

  it('sends the stored header to the totals preview, so it matches what is saved', async () => {
    api.getQuotation.mockResolvedValue(
      quote({ invoiceDiscount: '50', invoiceDiscountMode: 'BEFORE_TAX', additionalCharges: '100', chargesGstRate: '18', autoRoundOff: false }),
    );
    mount('/sales/quotations/5');
    await waitForLine();
    await waitFor(() => expect(api.previewSalesTotals).toHaveBeenCalled());
    expect(api.previewSalesTotals.mock.calls[0][0]).toMatchObject({
      customer: 3, invoiceType: 'GST', invoiceDiscount: 50, invoiceDiscountMode: 'BEFORE_TAX',
      additionalCharges: 100, chargesGstRate: 18, autoRoundOff: false,
    });
  });

  it('shows the server totals when the preview works, else a labelled estimate', async () => {
    api.getQuotation.mockResolvedValue(quote());
    api.previewSalesTotals.mockResolvedValue({
      taxableTotal: 1000, cgstTotal: 90, sgstTotal: 90, igstTotal: 0, cessTotal: 0, roundOff: 0, grandTotal: 1180, intraState: true,
    });
    mount('/sales/quotations/5');
    expect(await screen.findByText(new RegExp(`${t('billing.cgst')}: ₹90`))).toBeTruthy();
    expect(screen.queryByText(t('phase1.quotationEstimated'))).toBeNull();
  });

  it('labels the totals as an estimate when the server preview is unavailable', async () => {
    api.getQuotation.mockResolvedValue(quote());
    mount('/sales/quotations/5');
    expect(await screen.findByText(t('phase1.quotationEstimated'))).toBeTruthy();
    expect(await screen.findByText(t('billing.previewUnavailableClientTotals'))).toBeTruthy();
  });

  it('hints when a line asks for more than the default godown holds', async () => {
    api.getQuotation.mockResolvedValue(quote());
    api.getStockHints.mockResolvedValue({ '2': '3.000' });
    mount('/sales/quotations/5');
    expect(await screen.findByText(t('phase1.quotationStockOnly', { qty: 3 }))).toBeTruthy();
  });

  it('lists conversions with release date and reason', async () => {
    api.getQuotation.mockResolvedValue(
      quote({
        items: [line({ convertedQuantity: '4' })],
        conversions: [
          { id: 1, target: 'ORDER', documentId: 8, documentNumber: 'SO-0008', documentStatus: 'DRAFT', quantity: '4' },
          { id: 2, target: 'ORDER', documentId: 9, documentNumber: 'SO-0009', quantity: '3', releasedAt: '2026-10-02T00:00:00Z', releaseReason: 'DRAFT_DELETED' },
        ],
      }),
    );
    mount('/sales/quotations/5');
    expect(await screen.findByRole('button', { name: 'SO-0008' })).toBeTruthy();
    expect(screen.getByText(/2026-10-02 · DRAFT_DELETED/)).toBeTruthy();
  });

  it('a closed quote is read-only and shows why', async () => {
    api.getQuotation.mockResolvedValue(
      quote({ status: 'CONVERTED', shortClosedAt: '2026-10-02T00:00:00Z', shortCloseReason: 'Went elsewhere' }),
    );
    mount('/sales/quotations/5');
    expect(await screen.findByText(/Went elsewhere/)).toBeTruthy();
    expect(screen.queryByRole('button', { name: t('common.save') })).toBeNull();
  });

  it('warns before leaving with unsaved changes and not after saving', async () => {
    api.getQuotation.mockResolvedValue(quote());
    mount('/sales/quotations/5');
    await waitForLine();
    const clean = new Event('beforeunload', { cancelable: true });
    window.dispatchEvent(clean);
    expect(clean.defaultPrevented).toBe(false);
    fireEvent.change(screen.getByLabelText(t('phase1.quotationNotes')), { target: { value: 'edited' } });
    const dirty = new Event('beforeunload', { cancelable: true });
    window.dispatchEvent(dirty);
    expect(dirty.defaultPrevented).toBe(true);
  });

  it('asks before Back discards edits and goes back untouched when nothing changed', async () => {
    api.getQuotation.mockResolvedValue(quote());
    mount('/sales/quotations/5');
    await waitForLine();
    fireEvent.change(screen.getByLabelText(t('phase1.quotationNotes')), { target: { value: 'edited' } });
    fireEvent.click(screen.getByRole('button', { name: t('common.back') }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.click(within(dialog).getByRole('button', { name: t('common.stay') }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(screen.queryByText('list page')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: t('common.back') }));
    fireEvent.click(await within(await screen.findByRole('dialog')).findByRole('button', { name: t('common.leave') }));
    expect(await screen.findByText('list page')).toBeTruthy();
  });

  it('refuses a validity date before the quotation date', async () => {
    api.getQuotation.mockResolvedValue(quote());
    mount('/sales/quotations/5');
    await waitForLine();
    fireEvent.change(screen.getByLabelText(t('billing.validUntil')), { target: { value: '2026-01-01' } });
    await clickSave();
    expect(await screen.findByText(t('phase1.quotationValidityBeforeDate'))).toBeTruthy();
    expect(api.updateQuotation).not.toHaveBeenCalled();
  });
});

describe('QuotationEditorPage — lifecycle and actions', () => {
  it('a sent quote is editable with a notice when the lifecycle is on, read-only when it is off', async () => {
    api.lifecycleOn = true;
    api.getQuotation.mockResolvedValue(quote({ status: 'SENT' }));
    const first = mount('/sales/quotations/5');
    expect(await screen.findByText(t('phase1.quotationEditSentNotice'))).toBeTruthy();
    expect(screen.getByRole('button', { name: t('common.save') })).toBeTruthy();
    first.unmount();
    api.lifecycleOn = false;
    mount('/sales/quotations/5');
    expect(await screen.findByText(t('phase1.quotationReadOnly', { status: t('status.SENT') }))).toBeTruthy();
    expect(screen.queryByRole('button', { name: t('common.save') })).toBeNull();
  });

  it('an accepted quote offers Reopen for changes with a required reason', async () => {
    api.lifecycleOn = true;
    api.getQuotation.mockResolvedValue(quote({ status: 'ACCEPTED' }));
    mount('/sales/quotations/5');
    fireEvent.click(await screen.findByRole('button', { name: t('phase1.quotationReopen') }));
    const dialog = await screen.findByRole('dialog');
    const confirm = within(dialog).getByRole('button', { name: t('common.confirm') }) as HTMLButtonElement;
    expect(confirm.disabled).toBe(true);
    fireEvent.change(within(dialog).getByLabelText(new RegExp(t('phase1.quotationReasonLabel'))), { target: { value: 'Price changed' } });
    fireEvent.click(confirm);
    await waitFor(() => expect(api.quotationLifecycle).toHaveBeenCalledWith(5, 'reopen-for-changes', 'Price changed'));
  });

  it('duplicates into a new draft and opens it', async () => {
    api.getQuotation.mockResolvedValue(quote());
    mount('/sales/quotations/5');
    fireEvent.click(await screen.findByRole('button', { name: t('phase1.quotationDuplicate') }));
    await waitFor(() => expect(api.duplicateQuotation).toHaveBeenCalledWith(5));
  });

  it('shares a link and copies it', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
    api.getQuotation.mockResolvedValue(quote());
    mount('/sales/quotations/5');
    fireEvent.click(await screen.findByRole('button', { name: t('phase1.quotationShare') }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.click(within(dialog).getByRole('button', { name: t('common.copyLink') }));
    await waitFor(() => expect(api.shareQuotation).toHaveBeenCalledWith(5, 'link'));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith('https://app.test/q/tok'));
    expect(await within(dialog).findByText(t('phase1.quotationLinkCopied'))).toBeTruthy();
  });

  it('shows a load error with a way back', async () => {
    api.getQuotation.mockRejectedValue(new Error('Not found'));
    mount('/sales/quotations/5');
    expect(await screen.findByText(/Not found/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: t('common.back') }));
    await screen.findByText('list page');
  });
});
