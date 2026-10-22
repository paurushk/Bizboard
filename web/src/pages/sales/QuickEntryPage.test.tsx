import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import type { ReactElement } from 'react';
import axe from 'axe-core';
import { setLocale } from '@/i18n';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { QuickEntryPage } from '@/pages/sales/QuickEntryPage';
import type { Customer, Product } from '@/types/domain';

const PRODUCT: Product = {
  id: 7,
  name: 'Widget',
  sku: 'WID-1',
  sellingPrice: '50',
  gstRate: '18',
  status: 'ACTIVE',
  unitName: '',
  unitUqc: 'PCS',
} as Product;

const KG_PRODUCT: Product = {
  id: 8,
  name: 'Rice',
  sku: 'RICE-1',
  sellingPrice: '60',
  gstRate: '5',
  status: 'ACTIVE',
  unitName: 'kg',
  unitUqc: 'KGS',
} as Product;

const CUSTOMER: Customer = { id: 3, name: 'Ravi Traders', status: 'ACTIVE' } as Customer;

const auth = { user: { id: 1, email: 'rep@x.test', fullName: 'Rep', role: 'STAFF', canCreateSales: true, companyId: 9 } };
vi.mock('@/auth/AuthContext', () => ({ useAuth: () => auth }));

const flags: Record<string, boolean> = {};
vi.mock('@/config/featureFlags', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/config/featureFlags')>()),
  isRuntimeFlagEnabled: (key: string) => Boolean(flags[key]),
  useFeatureFlagEpoch: () => 0,
}));

const createSalesInvoice = vi.fn(async (..._args: unknown[]) => ({ id: 555, number: '', status: 'DRAFT' }));
const createSalesOrder = vi.fn(async (..._args: unknown[]) => ({ id: 777, number: 'SO-7', status: 'DRAFT' }));
const confirmSalesOrder = vi.fn(async (..._args: unknown[]) => ({}));
const previewSalesTotals = vi.fn();
let company: Record<string, unknown> = { registrationType: 'REGULAR', priceMode: 'EXCLUSIVE', gstin: '29AAAAA0000A1ZY' };
let recents: { customers: Array<{ id: number; name: string }>; products: Array<{ id: number }> } = {
  customers: [],
  products: [],
};
let catalog: Product[] = [PRODUCT, KG_PRODUCT];
let customerExtra: Record<string, unknown> = {};
let failProductLookup = false;
let customerGate: Promise<void> | null = null;
let stockHints: Record<string, string> = {};
let priceLists: unknown[] = [];

vi.mock('@/api/resources', () => ({
  createSalesInvoice: (...args: unknown[]) => createSalesInvoice(...args),
  createSalesOrder: (...args: unknown[]) => createSalesOrder(...args),
  getCompany: async () => company,
  getCustomer: async (id: number) => {
    if (customerGate) await customerGate;
    return { ...CUSTOMER, id, name: id === 3 ? 'Ravi Traders' : `Customer ${id}`, ...customerExtra };
  },
  getQuickEntryRecents: async () => recents,
  getStockHints: async () => stockHints,
  listPriceLists: async () => priceLists,
  listProductsByIds: async (ids: number[]) => {
    if (failProductLookup) throw new Error('offline');
    return catalog.filter((p) => ids.includes(p.id));
  },
  previewSalesTotals: (...args: unknown[]) => previewSalesTotals(...args),
  previewPurchaseTotals: async () => ({}),
}));

vi.mock('@/api/osPlan', () => ({
  confirmSalesOrder: (...args: unknown[]) => confirmSalesOrder(...args),
}));

vi.mock('@/hooks/usePartySearch', () => ({
  useCustomerSearch: () => ({
    query: '',
    setQuery: vi.fn(),
    options: [CUSTOMER],
    isFetching: false,
    enabled: true,
  }),
}));

vi.mock('@/hooks/useProductSearch', () => ({
  PRODUCT_SEARCH_MIN_CHARS: 2,
  useProductSearch: () => ({
    productQuery: '',
    setProductQuery: vi.fn(),
    options: catalog,
    isFetching: false,
    truncated: false,
    helperText: undefined,
    enabled: true,
    count: catalog.length,
  }),
}));

vi.mock('@/lib/telemetry', () => ({ trackShopFloor: vi.fn() }));
vi.mock('@/components/agents/PasteOrderPanel', () => ({ PasteOrderPanel: () => <div data-testid="paste-order-panel" /> }));

const navigate = vi.fn();
vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>();
  return { ...actual, useNavigate: () => navigate };
});

function wrap(ui: ReactElement, url = '/sales/quick-entry') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[url]}>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

async function pickCustomer() {
  const customerInput = screen.getByLabelText(/search a customer/i);
  fireEvent.mouseDown(customerInput);
  fireEvent.change(customerInput, { target: { value: 'Ravi' } });
  fireEvent.click(await screen.findByText('Ravi Traders'));
}

async function addProduct(label = 'Widget · WID-1') {
  const productInput = screen.getByLabelText(/search a product/i);
  fireEvent.mouseDown(productInput);
  fireEvent.change(productInput, { target: { value: 'W' } });
  fireEvent.click(await screen.findByRole('option', { name: label }));
}

const saveNext = () => screen.getByRole('button', { name: /save (draft bill )?& next/i });
const saveOpen = () => screen.getByRole('button', { name: /save (draft bill )?& open/i });

describe('QuickEntryPage — QOS-0048 / Quick Order Entry', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    for (const k of Object.keys(flags)) delete flags[k];
    company = { registrationType: 'REGULAR', priceMode: 'EXCLUSIVE', gstin: '29AAAAA0000A1ZY' };
    recents = { customers: [], products: [] };
    catalog = [PRODUCT, KG_PRODUCT];
    customerExtra = {};
    failProductLookup = false;
    customerGate = null;
    stockHints = {};
    priceLists = [];
    auth.user.companyId = 9;
    createSalesInvoice.mockImplementation(async () => ({ id: 555, number: '', status: 'DRAFT' }));
  });

  it('requires a customer before saving, even with items added', async () => {
    wrap(<QuickEntryPage />);
    await addProduct();
    await waitFor(() => expect(screen.getByLabelText(/quantity for widget/i)).toBeTruthy());
    expect(await screen.findByText(/Pick a customer before saving/i)).toBeTruthy();
    expect(saveNext()).toBeDisabled();
    expect(saveOpen()).toBeDisabled();
  });

  it('QOE-00: saves a draft bill with product + quantity only (no price, no GST) and opens it', async () => {
    wrap(<QuickEntryPage />);
    await pickCustomer();
    await addProduct();
    fireEvent.click(await screen.findByLabelText(/increase quantity widget/i));
    await waitFor(() => expect(screen.getByLabelText(/quantity for widget/i)).toHaveValue('2'));

    fireEvent.click(saveOpen());

    await waitFor(() => expect(createSalesInvoice).toHaveBeenCalledTimes(1));
    const [payload, options] = createSalesInvoice.mock.calls[0] as [Record<string, unknown>, Record<string, string>];
    expect(payload.customer).toBe(3);
    expect(payload.items).toEqual([{ product: 7, quantity: 2 }]);
    expect(JSON.stringify(payload)).not.toMatch(/unitPrice|gstRate/);
    expect(options.clientSource).toBe('quick_entry');
    expect(options.idempotencyKey).toBeTruthy();
    await waitFor(() => expect(navigate).toHaveBeenCalledWith('/sales/history/555'));
  });

  it('QOE-04: a Composition company saves a NON_GST bill', async () => {
    company = { registrationType: 'COMPOSITION', priceMode: 'EXCLUSIVE' };
    wrap(<QuickEntryPage />);
    await pickCustomer();
    await addProduct();
    await waitFor(() => expect(saveNext()).toBeEnabled());
    // wait for the company query so the type is known
    await waitFor(() => {
      fireEvent.click(saveNext());
      expect(createSalesInvoice).toHaveBeenCalled();
    });
    const payload = createSalesInvoice.mock.calls[0][0] as Record<string, unknown>;
    expect(payload.invoiceType).toBe('NON_GST');
    expect(payload.priceMode).toBe('EXCLUSIVE');
  });

  it('QOE-03: recent chips are hydrated live and tapping one bumps quantity instead of duplicating', async () => {
    wrap(<QuickEntryPage />);
    await addProduct();
    const chip = await screen.findByRole('button', { name: /^Widget · WID-1/ });
    fireEvent.click(chip);
    await waitFor(() => expect(screen.getByLabelText(/quantity for widget/i)).toHaveValue('2'));
    expect(screen.getAllByLabelText(/quantity for widget/i)).toHaveLength(1);
    const stored = JSON.parse(localStorage.getItem('bizboard:quick-entry-recent-skus-v2:9') ?? '[]');
    expect(stored).toEqual([{ id: 7, name: 'Widget', sku: 'WID-1' }]);
    expect(JSON.stringify(stored)).not.toMatch(/sellingPrice|gstRate/);
  });

  it('QOE-03: products that are gone or inactive are pruned from the device', async () => {
    localStorage.setItem(
      'bizboard:quick-entry-recent-skus-v2:9',
      JSON.stringify([
        { id: 7, name: 'Widget', sku: 'WID-1' },
        { id: 99, name: 'Ghost', sku: 'G-1' },
      ]),
    );
    wrap(<QuickEntryPage />);
    expect(await screen.findByRole('button', { name: /^Widget · WID-1/ })).toBeTruthy();
    await waitFor(() => {
      const stored = JSON.parse(localStorage.getItem('bizboard:quick-entry-recent-skus-v2:9') ?? '[]');
      expect(stored.map((p: { id: number }) => p.id)).toEqual([7]);
    });
    expect(screen.queryByText(/Ghost/)).toBeNull();
  });

  it('QOE-06: shows the rep\'s recent customers from the server', async () => {
    recents = { customers: [{ id: 3, name: 'Ravi Traders' }], products: [] };
    wrap(<QuickEntryPage />);
    fireEvent.click(await screen.findByRole('button', { name: 'Ravi Traders' }));
    expect(await screen.findByText('Ravi Traders')).toBeTruthy();
  });

  it('QOE-07: quantity can be typed, fractional only for measured units, and − never deletes a line', async () => {
    wrap(<QuickEntryPage />);
    await addProduct();
    const qty = await screen.findByLabelText(/quantity for widget/i);
    fireEvent.change(qty, { target: { value: '25' } });
    fireEvent.blur(qty);
    await waitFor(() => expect(qty).toHaveValue('25'));

    fireEvent.change(qty, { target: { value: '2.5' } }); // not valid for PCS
    fireEvent.blur(qty);
    await waitFor(() => expect(qty).toHaveValue('25'));

    fireEvent.change(qty, { target: { value: '1' } });
    fireEvent.blur(qty);
    await waitFor(() => expect(qty).toHaveValue('1'));
    expect(screen.getByLabelText(/decrease quantity widget/i)).toBeDisabled();
    expect(screen.getAllByLabelText(/quantity for widget/i)).toHaveLength(1);

    await addProduct('Rice · RICE-1 · kg');
    const kg = await screen.findByLabelText(/quantity for rice/i);
    fireEvent.change(kg, { target: { value: '2.5' } });
    fireEvent.blur(kg);
    await waitFor(() => expect(kg).toHaveValue('2.5'));
  });

  it('QOE-07: deleting a line offers Undo', async () => {
    wrap(<QuickEntryPage />);
    await addProduct();
    fireEvent.click(await screen.findByLabelText(/remove widget/i));
    expect(screen.queryByLabelText(/quantity for widget/i)).toBeNull();
    fireEvent.click(await screen.findByRole('button', { name: /undo/i }));
    expect(await screen.findByLabelText(/quantity for widget/i)).toBeTruthy();
  });

  it('QOE-08: Save & next resets the sheet and links to the saved document', async () => {
    wrap(<QuickEntryPage />);
    await pickCustomer();
    await addProduct();
    fireEvent.click(saveNext());
    await waitFor(() => expect(createSalesInvoice).toHaveBeenCalledTimes(1));
    expect(await screen.findByText(/Draft bill #555 saved/)).toBeTruthy();
    expect(navigate).not.toHaveBeenCalled();
    expect(screen.queryByLabelText(/quantity for widget/i)).toBeNull();
    expect(screen.getByRole('link', { name: /open/i })).toHaveAttribute('href', '/sales/history/555');
  });

  it('QOE-08: ?customer= pre-selects an active customer', async () => {
    wrap(<QuickEntryPage />, '/sales/quick-entry?customer=3');
    expect(await screen.findByText('Ravi Traders')).toBeTruthy();
    expect(screen.queryByLabelText(/search a customer/i)).toBeNull();
  });

  it('QOE-05: one tap saves once; a retry after a failure re-sends the SAME idempotency key, an edit gets a new one', async () => {
    createSalesInvoice.mockRejectedValueOnce(new Error('network down'));
    wrap(<QuickEntryPage />);
    await pickCustomer();
    await addProduct();

    fireEvent.click(saveNext());
    fireEvent.click(saveNext()); // double tap
    await waitFor(() => expect(createSalesInvoice).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.getByRole('alert')).toBeTruthy());

    fireEvent.click(saveNext());
    await waitFor(() => expect(createSalesInvoice).toHaveBeenCalledTimes(2));
    const first = (createSalesInvoice.mock.calls[0][1] as { idempotencyKey: string }).idempotencyKey;
    const second = (createSalesInvoice.mock.calls[1][1] as { idempotencyKey: string }).idempotencyKey;
    expect(second).toBe(first);

    // after success the sheet is empty; a fresh order gets a fresh key
    await pickCustomer();
    await addProduct();
    fireEvent.click(saveNext());
    await waitFor(() => expect(createSalesInvoice).toHaveBeenCalledTimes(3));
    expect((createSalesInvoice.mock.calls[2][1] as { idempotencyKey: string }).idempotencyKey).not.toBe(first);
  });

  it('QOE-02: with the order flag on, Save creates a sales order and shows it as saved', async () => {
    flags.QUICK_ENTRY_ORDER_MODE = true;
    wrap(<QuickEntryPage />);
    await pickCustomer();
    await addProduct();
    fireEvent.click(saveNext());
    await waitFor(() => expect(createSalesOrder).toHaveBeenCalledTimes(1));
    expect(createSalesInvoice).not.toHaveBeenCalled();
    const payload = createSalesOrder.mock.calls[0][0] as Record<string, unknown>;
    expect(payload.priceMode).toBe('EXCLUSIVE');
    expect(payload.items).toEqual([{ product: 7, quantity: 1 }]);
    expect(confirmSalesOrder).not.toHaveBeenCalled();
    expect(await screen.findByText(/Order SO-7 saved\./)).toBeTruthy();
  });

  it('QOE-02: auto-confirm confirms the order with its own idempotency key', async () => {
    flags.QUICK_ENTRY_ORDER_MODE = true;
    flags.QUICK_ENTRY_AUTO_CONFIRM = true;
    wrap(<QuickEntryPage />);
    await pickCustomer();
    await addProduct();
    fireEvent.click(saveNext());
    await waitFor(() => expect(confirmSalesOrder).toHaveBeenCalledTimes(1));
    const [id, , opts] = confirmSalesOrder.mock.calls[0] as [number, unknown, { idempotencyKey: string }];
    expect(id).toBe(777);
    expect(opts.idempotencyKey).toMatch(/-confirm$/);
    expect(await screen.findByText(/saved and confirmed/i)).toBeTruthy();
  });

  it('QOE-02: a gate failure at confirm leaves the order as a draft and says it needs approval', async () => {
    flags.QUICK_ENTRY_ORDER_MODE = true;
    flags.QUICK_ENTRY_AUTO_CONFIRM = true;
    confirmSalesOrder.mockRejectedValueOnce(Object.assign(new Error('Credit limit exceeded'), { response: { status: 400 } }));
    wrap(<QuickEntryPage />);
    await pickCustomer();
    await addProduct();
    fireEvent.click(saveNext());
    expect(await screen.findByText(/saved as a draft\. Needs approval: Credit limit exceeded/i)).toBeTruthy();
    expect(createSalesOrder).toHaveBeenCalledTimes(1);
  });

  it('D-6: an INCLUSIVE-price company books an order with price mode INCLUSIVE', async () => {
    flags.QUICK_ENTRY_ORDER_MODE = true;
    company = { registrationType: 'REGULAR', priceMode: 'INCLUSIVE', gstin: '29AAAAA0000A1ZY' };
    wrap(<QuickEntryPage />);
    await pickCustomer();
    await addProduct();
    await waitFor(() => expect(saveNext()).toBeEnabled());
    await waitFor(() => {
      fireEvent.click(saveNext());
      expect(createSalesOrder).toHaveBeenCalled();
    });
    expect((createSalesOrder.mock.calls[0][0] as Record<string, unknown>).priceMode).toBe('INCLUSIVE');
  });

  it('QOE-01: with the preview flag on, lines show the server price, price list name and server totals', async () => {
    flags.QUICK_ENTRY_PRICE_PREVIEW = true;
    previewSalesTotals.mockResolvedValue({
      subtotal: 80,
      taxableTotal: 80,
      taxTotal: 14.4,
      roundOff: 0.4,
      grandTotal: 94.8,
      items: [{ product: 7, unitPrice: 80, gstRate: 18, appliedPriceListName: 'Wholesale', unitName: '', uqcCode: 'PCS' }],
    });
    wrap(<QuickEntryPage />);
    await pickCustomer();
    await addProduct();
    expect(await screen.findByText('Wholesale', undefined, { timeout: 3000 })).toBeTruthy();
    expect(await screen.findByText('₹94.80', { exact: false })).toBeTruthy();
    const body = previewSalesTotals.mock.calls[0][0] as { items: unknown[]; customer: number };
    expect(body.customer).toBe(3);
    expect(body.items).toEqual([{ product: 7, quantity: 1 }]);
  });

  it('QOE-14: an unsaved order is restored after a reload', async () => {
    const first = wrap(<QuickEntryPage />);
    await pickCustomer();
    await addProduct();
    await waitFor(
      () => expect(localStorage.getItem('bizboard:draft:v1:9:1:quick-entry')).toBeTruthy(),
      { timeout: 3000 },
    );
    first.unmount();

    wrap(<QuickEntryPage />);
    expect(await screen.findByText(/Resume your unsaved order for Ravi Traders/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /^resume$/i }));
    expect(await screen.findByLabelText(/quantity for widget/i)).toBeTruthy();
    expect(await screen.findByText('Ravi Traders')).toBeTruthy();
  });

  it('QOE-14: discarding a draft removes it', async () => {
    localStorage.setItem(
      'bizboard:draft:v1:9:1:quick-entry',
      JSON.stringify({
        version: 1,
        savedAt: new Date().toISOString(),
        payload: { customerId: null, customerName: '', mode: 'bill', note: '', lines: [{ productId: 7, quantity: 3 }] },
      }),
    );
    wrap(<QuickEntryPage />);
    fireEvent.click(await screen.findByRole('button', { name: /discard/i }));
    expect(localStorage.getItem('bizboard:draft:v1:9:1:quick-entry')).toBeNull();
  });

  it('QOE-06: switching company clears the customer and lines', async () => {
    const view = wrap(<QuickEntryPage />);
    await pickCustomer();
    await addProduct();
    expect(await screen.findByLabelText(/quantity for widget/i)).toBeTruthy();
    auth.user.companyId = 10;
    act(() => {
      view.rerender(
        <QueryClientProvider client={new QueryClient()}>
          <MemoryRouter>
            <QuickEntryPage />
          </MemoryRouter>
        </QueryClientProvider>,
      );
    });
    await waitFor(() => expect(screen.queryByLabelText(/quantity for widget/i)).toBeNull());
    within(document.body).getByLabelText(/search a customer/i);
  });

  it('QOE-02: a dropped connection while confirming is NOT reported as a rule that needs approval', async () => {
    flags.QUICK_ENTRY_ORDER_MODE = true;
    flags.QUICK_ENTRY_AUTO_CONFIRM = true;
    confirmSalesOrder.mockRejectedValueOnce(new Error('Network Error'));
    wrap(<QuickEntryPage />);
    await pickCustomer();
    await addProduct();
    fireEvent.click(saveNext());
    expect(await screen.findByText(/confirming it did not complete/i)).toBeTruthy();
    expect(screen.queryByText(/Needs approval/i)).toBeNull();
  });

  it('QOE-09: a short line warns when negative stock is blocked, and only informs when it is allowed', async () => {
    stockHints = { '7': '1' };
    company = { registrationType: 'REGULAR', priceMode: 'EXCLUSIVE', negativeStockPolicy: 'BLOCK' };
    const first = wrap(<QuickEntryPage />);
    await addProduct();
    fireEvent.click(await screen.findByLabelText(/increase quantity widget/i));
    const chip = await screen.findByText('Only 1 in stock');
    expect(chip.closest('.MuiChip-root')).toHaveClass('MuiChip-colorWarning');
    first.unmount();

    localStorage.clear();
    company = { registrationType: 'REGULAR', priceMode: 'EXCLUSIVE', negativeStockPolicy: 'WARN' };
    wrap(<QuickEntryPage />);
    await addProduct();
    fireEvent.click(await screen.findByLabelText(/increase quantity widget/i));
    const info = await screen.findByText('Only 1 in stock');
    expect(info.closest('.MuiChip-root')).toHaveClass('MuiChip-colorInfo');
  });

  it('QOE-09: recent chips show how many are in stock', async () => {
    stockHints = { '7': '12' };
    localStorage.setItem(
      'bizboard:quick-entry-recent-skus-v2:9',
      JSON.stringify([{ id: 7, name: 'Widget', sku: 'WID-1' }]),
    );
    wrap(<QuickEntryPage />);
    expect(await screen.findByRole('button', { name: /Widget · WID-1 · 12 in stock/ })).toBeTruthy();
  });

  it('QOE-09: warns when the order would exceed the credit limit, and for a customer on credit hold', async () => {
    customerExtra = { creditLimit: '100', creditExposure: '90' };
    const first = wrap(<QuickEntryPage />);
    await pickCustomer();
    await addProduct();
    expect(await screen.findByText(/over their credit limit/i)).toBeTruthy();
    first.unmount();

    customerExtra = { collectionStatus: 'stop_credit' };
    wrap(<QuickEntryPage />);
    await pickCustomer();
    expect(await screen.findByText(/on a credit hold/i)).toBeTruthy();
  });

  it('QOE-09: a customer with several addresses can pick the delivery address, which is sent as shipTo', async () => {
    flags.QUICK_ENTRY_ORDER_MODE = true;
    customerExtra = {
      shippingAddresses: [
        { id: 11, label: 'Main', address: 'Main Rd', isDefault: true },
        { id: 12, label: 'Depot', address: 'Depot St' },
      ],
    };
    wrap(<QuickEntryPage />);
    await pickCustomer();
    await addProduct();
    fireEvent.mouseDown(await screen.findByLabelText(/deliver to/i));
    fireEvent.click(await screen.findByRole('option', { name: /Depot: Depot St/ }));
    fireEvent.click(saveNext());
    await waitFor(() => expect(createSalesOrder).toHaveBeenCalled());
    expect((createSalesOrder.mock.calls[0][0] as Record<string, unknown>).shipTo).toBe(12);
  });

  it('QOE-14: the chosen delivery address is part of the saved draft', async () => {
    flags.QUICK_ENTRY_ORDER_MODE = true;
    customerExtra = { shippingAddresses: [{ id: 11, address: 'A' }, { id: 12, address: 'B' }] };
    wrap(<QuickEntryPage />);
    await pickCustomer();
    await addProduct();
    fireEvent.mouseDown(await screen.findByLabelText(/deliver to/i));
    fireEvent.click(await screen.findByRole('option', { name: 'B' }));
    await waitFor(
      () => {
        const draft = JSON.parse(localStorage.getItem('bizboard:draft:v1:9:1:quick-entry') ?? '{}');
        expect(draft.payload?.shipToId).toBe(12);
      },
      { timeout: 3000 },
    );
  });

  it('QOE-08: ?product= adds that product once', async () => {
    wrap(<QuickEntryPage />, '/sales/quick-entry?product=7');
    expect(await screen.findByLabelText(/quantity for widget/i)).toHaveValue('1');
    expect(screen.getAllByLabelText(/quantity for widget/i)).toHaveLength(1);
  });

  it('QOE-04: with the server preview off, the footer shows an estimated GST instead of a bare pre-tax total', async () => {
    wrap(<QuickEntryPage />);
    await addProduct();
    expect(await screen.findByText(/Estimated GST/)).toBeTruthy();
    expect(screen.getAllByText('₹59.00', { exact: false }).length).toBeGreaterThan(0);
  });

  it("QOE-01: with the preview off, the customer's price list still prices the line (client fallback)", async () => {
    customerExtra = { priceList: 5 };
    priceLists = [{ id: 5, name: 'Wholesale', items: [{ product: 7, unitPrice: '40', minQty: '1' }] }];
    wrap(<QuickEntryPage />);
    await pickCustomer();
    await addProduct();
    expect(await screen.findByText('Wholesale')).toBeTruthy();
    expect(screen.getAllByText('₹40.00', { exact: false }).length).toBeGreaterThan(0);
  });

  it('QOE-01: a failed preview falls back to catalogue prices with the indicative note', async () => {
    flags.QUICK_ENTRY_PRICE_PREVIEW = true;
    previewSalesTotals.mockRejectedValue(new Error('boom'));
    wrap(<QuickEntryPage />);
    await pickCustomer();
    await addProduct();
    expect(await screen.findByText(/confirmed when the document is saved/i)).toBeTruthy();
    expect(screen.getAllByText('₹50.00', { exact: false }).length).toBeGreaterThan(0);
  });

  it('QOE-10: switching the language re-renders the page', async () => {
    wrap(<QuickEntryPage />);
    expect(screen.getByText('Add an item')).toBeTruthy();
    act(() => setLocale('hi'));
    expect(await screen.findByText('आइटम जोड़ें')).toBeTruthy();
    act(() => setLocale('en'));
  });

  it('QOE-10: line controls are named after the product and are at least 44px', async () => {
    wrap(<QuickEntryPage />);
    await addProduct();
    for (const name of [/increase quantity widget/i, /decrease quantity widget/i, /remove widget/i]) {
      const button = await screen.findByLabelText(name);
      expect(button).toBeTruthy();
      expect(getComputedStyle(button).width).toBe('44px');
    }
  });

  it('QOE-10: has no accessibility violations with an order in progress', async () => {
    wrap(<QuickEntryPage />);
    await pickCustomer();
    await addProduct();
    await screen.findByLabelText(/quantity for widget/i);
    const results = await axe.run(document.body, {
      rules: { 'color-contrast': { enabled: false }, region: { enabled: false } },
    });
    expect(results.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(' ')).join(' | ')}`)).toEqual([]);
  });

  it('review: a failed restore keeps the saved draft so the rep can try again', async () => {
    localStorage.setItem(
      'bizboard:draft:v1:9:1:quick-entry',
      JSON.stringify({
        version: 1,
        savedAt: new Date().toISOString(),
        payload: { customerId: null, customerName: '', mode: 'bill', note: '', lines: [{ productId: 7, quantity: 3 }] },
      }),
    );
    wrap(<QuickEntryPage />);
    const resume = await screen.findByRole('button', { name: /^resume$/i });
    failProductLookup = true; // the product lookup fails while restoring
    fireEvent.click(resume);
    expect(await screen.findByRole('alert')).toBeTruthy();
    expect(localStorage.getItem('bizboard:draft:v1:9:1:quick-entry')).not.toBeNull();
  });

  it('review: a retry sends the same idempotency key only while the request body is unchanged (company data included)', async () => {
    company = { registrationType: 'REGULAR', priceMode: 'EXCLUSIVE', gstin: '29AAAAA0000A1ZY' };
    createSalesInvoice.mockRejectedValueOnce(new Error('network down'));
    wrap(<QuickEntryPage />);
    await pickCustomer();
    await addProduct();
    await waitFor(() => expect(saveNext()).toBeEnabled());
    fireEvent.click(saveNext());
    await waitFor(() => expect(createSalesInvoice).toHaveBeenCalledTimes(1));
    const first = createSalesInvoice.mock.calls[0];
    // the body now carries invoiceType/priceMode once the company has loaded; the key is tied to that body
    expect((first[0] as Record<string, unknown>).priceMode).toBe('EXCLUSIVE');
    await waitFor(() => expect(screen.getByRole('alert')).toBeTruthy());
    fireEvent.click(saveNext());
    await waitFor(() => expect(createSalesInvoice).toHaveBeenCalledTimes(2));
    expect((createSalesInvoice.mock.calls[1][1] as { idempotencyKey: string }).idempotencyKey).toBe(
      (first[1] as { idempotencyKey: string }).idempotencyKey,
    );
    expect(createSalesInvoice.mock.calls[1][0]).toEqual(first[0]);
  });

  it('review: a 409 or 429 while confirming is unknown, not "needs approval"', async () => {
    flags.QUICK_ENTRY_ORDER_MODE = true;
    flags.QUICK_ENTRY_AUTO_CONFIRM = true;
    confirmSalesOrder.mockRejectedValueOnce(Object.assign(new Error('busy'), { response: { status: 409 } }));
    wrap(<QuickEntryPage />);
    await pickCustomer();
    await addProduct();
    fireEvent.click(saveNext());
    expect(await screen.findByText(/confirming it did not complete/i)).toBeTruthy();
    expect(screen.queryByText(/Needs approval/i)).toBeNull();
  });

  it("review: the delivery address is cleared when the rep changes customer", async () => {
    flags.QUICK_ENTRY_ORDER_MODE = true;
    customerExtra = { shippingAddresses: [{ id: 11, address: 'A' }, { id: 12, address: 'B' }] };
    wrap(<QuickEntryPage />);
    await pickCustomer();
    await addProduct();
    fireEvent.mouseDown(await screen.findByLabelText(/deliver to/i));
    fireEvent.click(await screen.findByRole('option', { name: 'B' }));
    fireEvent.click(document.querySelector('.MuiChip-deleteIcon') as Element); // clear the customer chip
    await pickCustomer();
    fireEvent.click(await screen.findByRole('button', { name: /Save & next order/ }));
    await waitFor(() => expect(createSalesOrder).toHaveBeenCalled());
    expect((createSalesOrder.mock.calls[0][0] as Record<string, unknown>).shipTo).toBeUndefined();
  });

  it('review: saving waits for the full customer record so a GST customer is not billed as RETAIL', async () => {
    recents = { customers: [{ id: 3, name: 'Ravi Traders' }], products: [] };
    customerExtra = { gstin: '29AAAAA0000A1ZY' };
    let release: () => void = () => undefined;
    customerGate = new Promise<void>((resolve) => {
      release = resolve;
    });
    wrap(<QuickEntryPage />);
    fireEvent.click(await screen.findByRole('button', { name: 'Ravi Traders' }));
    await addProduct();
    expect(saveNext()).toBeDisabled(); // the full customer record has not arrived yet
    release();
    await waitFor(() => expect(saveNext()).toBeEnabled(), { timeout: 3000 });
    fireEvent.click(saveNext());
    await waitFor(() => expect(createSalesInvoice).toHaveBeenCalled());
    expect((createSalesInvoice.mock.calls[0][0] as Record<string, unknown>).invoiceType).toBe('GST');
  });

  it('shows the paste-order panel in order mode only, never in draft-bill mode', async () => {
    flags.QUICK_ENTRY_ORDER_MODE = true;
    wrap(<QuickEntryPage />);
    expect(await screen.findByTestId('paste-order-panel')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Draft bill' }));
    await waitFor(() => expect(screen.queryByTestId('paste-order-panel')).toBeNull());
    fireEvent.click(screen.getByRole('button', { name: 'Sales order' }));
    expect(await screen.findByTestId('paste-order-panel')).toBeTruthy();
  });

  it('has no paste-order panel when order mode is not switched on', async () => {
    wrap(<QuickEntryPage />);
    await screen.findByLabelText(/search a customer/i);
    expect(screen.queryByTestId('paste-order-panel')).toBeNull();
  });
});
