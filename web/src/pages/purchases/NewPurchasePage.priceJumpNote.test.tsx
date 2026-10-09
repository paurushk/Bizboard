import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import userEvent from '@testing-library/user-event';
import type { ReactElement } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { NewPurchasePage } from '@/pages/purchases/NewPurchasePage';
import { t } from '@/i18n';
import type { DraftLine } from '@/components/billing';

// Price-jump note: NewPurchasePage wires DraftLineTable's `renderPriceHint`
// to a live, per-distinct-product lookup of `getSupplierPriceHistory`
// (see the `priceHistoryProductIds` / `priceJumpNote` wiring in
// NewPurchasePage.tsx). This suite exercises that wiring end to end rather
// than a pure function, because the dedup/caching behavior lives in the
// page's `useQueries` call, not in an extractable helper.

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 1, role: 'OWNER', companyId: 1 },
    isAuthenticated: true,
  }),
}));

vi.mock('@/hooks/useSubscriptionGate', () => ({
  useSubscriptionGate: () => ({ writesBlocked: false, subscription: null, isLoading: false }),
}));

vi.mock('@/hooks/useActiveCustomFieldDefs', () => ({
  useActiveCustomFieldDefs: () => [],
  useVisibleCustomFieldDefs: () => [],
}));

vi.mock('@/config/featureFlags', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/config/featureFlags')>();
  return {
    ...actual,
    isRuntimeFlagEnabled: (key: string) =>
      Boolean((globalThis as { __ff?: Record<string, boolean> }).__ff?.[key]),
    useFeatureFlagEpoch: () => 0,
  };
});

const getSupplierPriceHistory = vi.fn();

vi.mock('@/api/resources', () => ({
  getCompany: async () => ({
    id: 1,
    name: 'Shop',
    state: 'Karnataka',
    gstin: '',
    registrationType: 'REGULAR',
    isGstRegistered: false,
    accountingEnabled: false,
  }),
  getSupplier: async (id: number) => ({ id, name: 'Mega Suppliers', gstin: '', state: 'Karnataka' }),
  getSupplierPriceHistory: (...args: unknown[]) => getSupplierPriceHistory(...args),
  listSuppliersPage: async () => ({ results: [] }),
  listWarehouses: async () => [],
  listBillsOfEntryPage: async () => ({ results: [] }),
  listCompanyGstins: async () => [],
  listCostCenters: async () => [],
  listBatches: async () => [],
  listProductsPage: async () => ({ results: [] }),
  searchProducts: async () => [],
  listStock: async () => [],
  listPurchasesPage: async () => ({ results: [] }),
  getPurchaseNumberSeries: async () => ({ prefix: 'PUR', nextNumber: 1, padding: 5 }),
  getPurchase: vi.fn(),
  createPurchase: vi.fn(),
  updatePurchase: vi.fn(),
  completePurchase: vi.fn(),
  createSupplierPayment: vi.fn(),
  createAllocation: vi.fn(),
  createProduct: vi.fn(),
  createSupplier: vi.fn(),
  updateSupplier: vi.fn(),
  uploadFile: vi.fn(),
  previewPurchaseTotals: async () => ({
    subtotal: 0,
    discountTotal: 0,
    taxableTotal: 0,
    cgstTotal: 0,
    sgstTotal: 0,
    igstTotal: 0,
    cessTotal: 0,
    roundOff: 0,
    grandTotal: 0,
    taxTotal: 0,
  }),
  previewSalesTotals: vi.fn(),
}));

vi.mock('@/pages/purchases/usePurchaseOffline', () => ({
  usePurchaseOffline: () => undefined,
}));

const loadPurchaseDraft = vi.fn();

vi.mock('@/offline/invoiceDraftCache', () => ({
  loadPurchaseDraft: (...args: unknown[]) => loadPurchaseDraft(...args),
  savePurchaseDraft: vi.fn().mockResolvedValue(undefined),
  clearPurchaseDraft: vi.fn().mockResolvedValue(undefined),
  enqueueDraft: vi.fn().mockResolvedValue(undefined),
  OUTBOX_WARNING_DISMISS_KEY: 'bizboard.dismiss.outboxPlaintext',
}));

function wrap(ui: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/purchases/new']}>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

const BASE_LINE: DraftLine = {
  key: 'l1',
  product: 7,
  productName: 'Widget A',
  description: '',
  sku: 'WID-A',
  hsnCode: '998811',
  unitName: 'PCS',
  batchNo: '',
  expDate: '',
  mfgDate: '',
  mrp: 0,
  quantity: 1,
  unitPrice: 15,
  discountPercent: 0,
  discountAmount: 0,
  gstRate: 0,
  cessRate: 0,
  taxableAmount: 15,
  cgst: 0,
  sgst: 0,
  igst: 0,
  cess: 0,
  lineTotal: 15,
  gross: 15,
};

function makeLine(overrides: Partial<DraftLine>): DraftLine {
  return { ...BASE_LINE, ...overrides };
}

/** Drives the page through its existing "restore local draft" flow to set
 * `supplierId`/`lines` directly — the same production code path
 * (applyPendingDraft) the autosave banner uses, without fighting the
 * product/supplier autocompletes just to get fixture lines onto the page. */
async function restoreDraft(payload: Record<string, unknown>) {
  loadPurchaseDraft.mockResolvedValue({ savedAt: new Date().toISOString(), payload });
  wrap(<NewPurchasePage />);
  const restoreBtn = await screen.findByRole('button', { name: t('billing.restoreDraft') });
  await userEvent.click(restoreBtn);
}

describe('NewPurchasePage price-jump note', () => {
  beforeEach(() => {
    (globalThis as { __ff?: Record<string, boolean> }).__ff = {
      ENABLE_SUPPLIER_PRICE_HISTORY: true,
    };
    getSupplierPriceHistory.mockReset();
    loadPurchaseDraft.mockReset();
  });

  it('shows the price-jump note with the correct rate and date when the entered rate is higher than history', async () => {
    getSupplierPriceHistory.mockResolvedValue({
      rows: [
        { source: 'PURCHASE_INVOICE', documentDate: '2026-01-01', unitPrice: '10.00' },
      ],
    });
    await restoreDraft({
      supplierId: 3,
      lines: [makeLine({ unitPrice: 15 })],
    });

    expect(await screen.findByText('last bill was ₹10.00 on 2026-01-01')).toBeTruthy();
    expect(getSupplierPriceHistory).toHaveBeenCalledWith(3, 7);
  });

  it('shows no note when the entered rate is equal to or lower than history', async () => {
    getSupplierPriceHistory.mockResolvedValue({
      rows: [
        { source: 'PURCHASE_INVOICE', documentDate: '2026-01-01', unitPrice: '10.00' },
      ],
    });
    await restoreDraft({
      supplierId: 3,
      lines: [
        makeLine({ key: 'equal', unitPrice: 10 }),
        makeLine({ key: 'lower', product: 7, productName: 'Widget A (lower)', unitPrice: 8 }),
      ],
    });

    // Let the price-history query resolve before asserting an absence.
    await screen.findByText('Widget A (lower)');
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.queryByText(/last bill was/)).toBeNull();
  });

  it('shows no note and does not error when there is no price history for the product+supplier', async () => {
    getSupplierPriceHistory.mockResolvedValue({ rows: [] });
    await restoreDraft({
      supplierId: 3,
      lines: [makeLine({ unitPrice: 15 })],
    });

    await screen.findByText('Widget A');
    expect((await screen.findAllByDisplayValue('15')).length).toBeGreaterThan(0);
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.queryByText(/last bill was/)).toBeNull();
  });

  it('does not re-fetch price history redundantly for the same product+supplier across multiple lines', async () => {
    getSupplierPriceHistory.mockResolvedValue({
      rows: [
        { source: 'PURCHASE_INVOICE', documentDate: '2026-01-01', unitPrice: '10.00' },
      ],
    });
    await restoreDraft({
      supplierId: 3,
      lines: [
        makeLine({ key: 'l1', product: 7, unitPrice: 15 }),
        makeLine({ key: 'l2', product: 7, productName: 'Widget A (batch 2)', unitPrice: 20 }),
      ],
    });

    const notes = await screen.findAllByText('last bill was ₹10.00 on 2026-01-01');
    expect(notes).toHaveLength(2);
    // One query per distinct product, not one per line sharing that product.
    expect(getSupplierPriceHistory).toHaveBeenCalledTimes(1);
    expect(getSupplierPriceHistory).toHaveBeenCalledWith(3, 7);
  });

  it('keeps purchase terms empty after the default paragraph is cleared', async () => {
    const user = userEvent.setup();
    wrap(<NewPurchasePage />);
    const terms = await screen.findByLabelText('Add Terms and Conditions');
    expect((terms as HTMLTextAreaElement).value).toContain('Goods received');
    await user.clear(terms);
    expect(terms).toHaveValue('');
  });
});
