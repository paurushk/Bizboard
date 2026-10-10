import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { configure, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { NewInvoicePage } from '@/pages/sales/NewInvoicePage';
import { draftKey } from '@/lib/deviceDraft';

// The whole editor mounts here, so give lookups the same headroom as the slow editor test.
configure({ asyncUtilTimeout: 20_000 });
vi.setConfig({ testTimeout: 40_000 });

const COMPANY_ID = 9;
const USER_ID = 1;

const api = vi.hoisted(() => ({
  getProduct: vi.fn(),
  getCustomer: vi.fn(async (id: number) => ({ id, name: 'Anil Store', status: 'ACTIVE', state: 'Delhi' })),
  listPriceLists: vi.fn(async () => [] as unknown[]),
}));

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({
    user: {
      id: 1,
      email: 'owner@bizboard.test',
      fullName: 'Owner',
      role: 'OWNER',
      companyId: 9,
      company: { registrationType: 'REGULAR', state: 'Delhi' },
    },
  }),
}));

vi.mock('@/hooks/useSubscriptionGate', () => ({
  useSubscriptionGate: () => ({ writesBlocked: false, isLoading: false }),
}));

vi.mock('@/api/resources', () => ({
  getCompany: async () => ({
    id: 9,
    name: 'Acme',
    registrationType: 'REGULAR',
    state: 'Delhi',
    gstin: '07AAAAA0000A1Z5',
    negativeStockPolicy: 'WARN',
  }),
  getProduct: (...args: unknown[]) => api.getProduct(...args),
  listSalesInvoicesPage: async () => ({ results: [], count: 0, next: null, previous: null }),
  listCustomersPage: async () => ({ results: [], count: 0, next: null, previous: null }),
  getCustomer: (...args: unknown[]) => api.getCustomer(...(args as [number])),
  listCollectionRisk: async () => [],
  listWarehouses: async () => [{ id: 1, name: 'Main Godown' }],
  listCompanyGstins: async () => [],
  listCostCenters: async () => [],
  listPriceLists: (...args: unknown[]) => api.listPriceLists(...(args as [])),
  listBatches: async () => [],
  getSalesInvoiceNumberSeries: async () => ({ prefix: 'INV', nextNumber: 1 }),
  getSalesInvoice: async () => ({ id: 1, number: 'INV-1' }),
  listProductsPage: async () => ({ results: [], count: 0, next: null, previous: null }),
  searchProducts: async () => [],
  listStock: async () => [],
  previewSalesTotals: async () => ({ subtotal: 0, grandTotal: 0, cgstTotal: 0, sgstTotal: 0, taxTotal: 0 }),
  previewSalesInvoiceTotals: async () => ({ subtotal: 0, grandTotal: 0, cgstTotal: 0, sgstTotal: 0, taxTotal: 0 }),
  createSalesInvoice: vi.fn(),
  updateSalesInvoice: vi.fn(),
  completeSalesInvoice: vi.fn(),
  downloadInvoicePdf: vi.fn(async () => new Blob(['%PDF'])),
  downloadInvoicePreviewPdf: vi.fn(async () => new Blob(['%PDF'])),
}));

const line = (id: number, name: string, extra: Record<string, unknown> = {}) => ({
  key: `l-${id}`,
  product: id,
  productName: name,
  description: '',
  sku: `SKU-${id}`,
  hsnCode: '',
  unitName: 'PCS',
  batchNo: '',
  expDate: '',
  mfgDate: '',
  mrp: 0,
  quantity: 2,
  unitPrice: 0,
  discountPercent: 0,
  discountAmount: 0,
  gstRate: 0,
  cessRate: 0,
  taxableAmount: 0,
  cgst: 0,
  sgst: 0,
  igst: 0,
  cess: 0,
  lineTotal: 0,
  gross: 0,
  ...extra,
});

const product = (id: number, name: string, sellingPrice: number) => ({
  id,
  name,
  sku: `SKU-${id}`,
  sellingPrice,
  unitName: 'PCS',
  status: 'ACTIVE',
  gstRate: 0,
});

function seedDraft(lines: unknown[], customerId: number | '' = '') {
  localStorage.setItem(
    draftKey(COMPANY_ID, USER_ID, 'sales-invoice'),
    JSON.stringify({ version: 1, savedAt: new Date().toISOString(), payload: { lines, customerId } }),
  );
}

const savedDraft = () => localStorage.getItem(draftKey(COMPANY_ID, USER_ID, 'sales-invoice'));

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/sales/new']}>
        <Routes>
          <Route path="/sales/new" element={<NewInvoicePage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const restoreButton = () => screen.findByRole('button', { name: /^restore$/i });

describe('NewInvoicePage restoring a saved draft', () => {
  beforeEach(() => {
    api.getProduct.mockReset();
    localStorage.clear();
  });

  afterEach(() => localStorage.clear());

  it('offers to restore a saved draft, and to discard it', async () => {
    seedDraft([line(5, 'Soap')]);
    renderPage();
    expect(await restoreButton()).toBeTruthy();
    expect(screen.getByRole('button', { name: /^discard$/i })).toBeTruthy();
  });

  it('offers nothing when there is no saved draft', async () => {
    renderPage();
    await screen.findByPlaceholderText(/search by customer name/i);
    expect(screen.queryByRole('button', { name: /^restore$/i })).toBeNull();
  });

  it('puts the saved lines back with the current price and fetches the products together', async () => {
    seedDraft([line(5, 'Soap'), line(6, 'Shampoo')]);
    api.getProduct.mockImplementation(async (id: number) =>
      id === 5 ? product(5, 'Soap', 40) : product(6, 'Shampoo', 120),
    );
    renderPage();
    await userEvent.click(await restoreButton());

    expect(await screen.findByText('Soap')).toBeTruthy();
    expect(screen.getByText('Shampoo')).toBeTruthy();
    expect(api.getProduct).toHaveBeenCalledTimes(2);
    expect(screen.queryByRole('button', { name: /^restore$/i })).toBeNull();
  });

  it('INV-MAIN-17 restores the party and a price the user typed', async () => {
    seedDraft([line(5, 'Soap', { unitPrice: 33, priceEdited: true })], 10);
    api.getProduct.mockResolvedValue(product(5, 'Soap', 40));
    renderPage();
    await userEvent.click(await restoreButton());
    expect(await screen.findByText('Soap')).toBeTruthy();
    expect(await screen.findByText('Anil Store')).toBeTruthy();
    expect(await screen.findByDisplayValue('33')).toBeTruthy();
  });

  it('keeps a price the user typed instead of replacing it with the catalogue price', async () => {
    seedDraft([line(5, 'Soap', { unitPrice: 33, priceEdited: true })]);
    api.getProduct.mockResolvedValue(product(5, 'Soap', 40));
    renderPage();
    await userEvent.click(await restoreButton());
    await screen.findByText('Soap');
    expect(await screen.findByDisplayValue('33')).toBeTruthy();
    expect(screen.queryByDisplayValue('40')).toBeNull();
  });

  describe('REVIEW price drift uses the draft party price list', () => {
    const listWith = (rate: number) => [
      { id: 3, name: 'Wholesale', isActive: true, items: [{ product: 5, unitPrice: rate, minQty: 1 }] },
    ];

    beforeEach(() => {
      api.getCustomer.mockClear();
      api.getCustomer.mockImplementation(async (id: number) => ({
        id, name: 'Anil Store', status: 'ACTIVE', state: 'Delhi', priceList: 3,
      }));
    });
    afterEach(() => {
      api.getCustomer.mockImplementation(async (id: number) => ({ id, name: 'Anil Store', status: 'ACTIVE', state: 'Delhi' }));
      api.listPriceLists.mockImplementation(async () => []);
    });

    it('fetches the party when it is not on the loaded page, so a list price is not mistaken for drift', async () => {
      api.listPriceLists.mockImplementation(async () => listWith(90));
      seedDraft([line(5, 'Soap', { unitPrice: 90 })], 10);
      api.getProduct.mockResolvedValue(product(5, 'Soap', 100));
      renderPage();
      await userEvent.click(await restoreButton());
      expect(await screen.findByText('Soap')).toBeTruthy();
      expect(api.getCustomer).toHaveBeenCalledWith(10);
      expect(screen.queryByRole('button', { name: /keep draft prices/i })).toBeNull();
      expect(await screen.findByDisplayValue('90')).toBeTruthy();
    });

    it('asks to keep or update when the party list price has moved, and keeps the draft price on request', async () => {
      api.listPriceLists.mockImplementation(async () => listWith(80));
      seedDraft([line(5, 'Soap', { unitPrice: 90 })], 10);
      api.getProduct.mockResolvedValue(product(5, 'Soap', 100));
      renderPage();
      await userEvent.click(await restoreButton());
      const keep = await screen.findByRole('button', { name: /keep draft prices/i });
      expect(screen.getByRole('button', { name: /update to current prices/i })).toBeTruthy();
      await userEvent.click(keep);
      expect(await screen.findByDisplayValue('90')).toBeTruthy();
    });

    it('updates to the party list price on request', async () => {
      api.listPriceLists.mockImplementation(async () => listWith(80));
      seedDraft([line(5, 'Soap', { unitPrice: 90 })], 10);
      api.getProduct.mockResolvedValue(product(5, 'Soap', 100));
      renderPage();
      await userEvent.click(await restoreButton());
      await userEvent.click(await screen.findByRole('button', { name: /update to current prices/i }));
      expect(await screen.findByDisplayValue('80')).toBeTruthy();
    });

    it('does not ask about a price the operator typed', async () => {
      api.listPriceLists.mockImplementation(async () => listWith(80));
      seedDraft([line(5, 'Soap', { unitPrice: 77, priceEdited: true })], 10);
      api.getProduct.mockResolvedValue(product(5, 'Soap', 100));
      renderPage();
      await userEvent.click(await restoreButton());
      expect(await screen.findByDisplayValue('77')).toBeTruthy();
      expect(screen.queryByRole('button', { name: /keep draft prices/i })).toBeNull();
    });
  });

  it('REVIEW the saved copy never carries the item purchase cost', async () => {
    api.getProduct.mockResolvedValue({ ...product(5, 'Soap', 100), purchasePrice: 61 });
    seedDraft([line(5, 'Soap', { unitPrice: 100, priceEdited: true })]);
    renderPage();
    await userEvent.click(await restoreButton());
    expect(await screen.findByText('Soap')).toBeTruthy();
    await waitFor(() => {
      const stored = JSON.parse(savedDraft() ?? 'null');
      expect(stored?.payload?.lines?.[0]).toBeTruthy();
      expect(stored.payload.lines[0].purchasePrice ?? null).toBeNull();
    });
  });

  it('keeps the whole draft, and says why, when the products cannot be fetched', async () => {
    seedDraft([line(5, 'Soap'), line(6, 'Shampoo')]);
    api.getProduct.mockRejectedValue(new Error('Network down'));
    renderPage();
    await userEvent.click(await restoreButton());

    expect(await screen.findByText(/Network down/)).toBeTruthy();
    // Nothing was thrown away: the offer is still there and the saved copy is intact.
    expect(screen.getByRole('button', { name: /^restore$/i })).toBeTruthy();
    const stored = JSON.parse(savedDraft() ?? 'null');
    expect(stored.payload.lines).toHaveLength(2);
    expect(screen.queryByText('Soap')).toBeNull();
  });

  it('drops only the item the server no longer has, and restores the rest', async () => {
    seedDraft([line(5, 'Soap'), line(6, 'Gone item')]);
    api.getProduct.mockImplementation(async (id: number) => {
      if (id === 6) throw Object.assign(new Error('Not found'), { response: { status: 404 } });
      return product(5, 'Soap', 40);
    });
    renderPage();
    await userEvent.click(await restoreButton());

    expect(await screen.findByText('Soap')).toBeTruthy();
    expect(screen.queryByText('Gone item')).toBeNull();
    expect(screen.queryByRole('button', { name: /^restore$/i })).toBeNull();
  });

  it('removes the saved copy when the user discards it', async () => {
    seedDraft([line(5, 'Soap')]);
    renderPage();
    await userEvent.click(await screen.findByRole('button', { name: /^discard$/i }));
    await waitFor(() => expect(screen.queryByRole('button', { name: /^restore$/i })).toBeNull());
    expect(savedDraft()).toBeNull();
    expect(api.getProduct).not.toHaveBeenCalled();
  });
});
