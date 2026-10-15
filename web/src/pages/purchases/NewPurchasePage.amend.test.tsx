import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { configure, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { NewPurchasePage } from '@/pages/purchases/NewPurchasePage';
import { registerGlobalConfirm } from '@/utils/confirmBridge';
import { t } from '@/i18n';

configure({ asyncUtilTimeout: 15_000 });
vi.setConfig({ testTimeout: 40_000 });

// Purchase review WP-1/WP-3/WP-7/WP-11: what the bill editor sends on Save & Complete and where it
// lands afterwards. Lines are restored through the real "restore local draft" path.

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ user: { id: 1, role: 'OWNER', companyId: 1 }, isAuthenticated: true }),
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
  return { ...actual, isRuntimeFlagEnabled: () => false, useFeatureFlagEpoch: () => 0 };
});

const api = vi.hoisted(() => ({
  getPurchase: vi.fn(),
  updatePurchase: vi.fn(),
  loadPurchaseDraft: vi.fn(),
  enqueueDraft: vi.fn(),
}));

vi.mock('@/api/resources', () => ({
  getCompany: async () => ({
    id: 1,
    name: 'Shop',
    state: 'Karnataka',
    gstin: '29AAAAA0000A1Z5',
    registrationType: 'REGULAR',
    isGstRegistered: true,
    accountingEnabled: false,
  }),
  getSupplier: async (id: number) => ({ id, name: 'Mega Suppliers', gstin: '', state: 'Karnataka' }),
  getSupplierPriceHistory: async () => ({ rows: [] }),
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
  getPurchase: (...a: unknown[]) => api.getPurchase(...a),
  createPurchase: vi.fn(),
  updatePurchase: (...a: unknown[]) => api.updatePurchase(...a),
  completePurchase: vi.fn(),
  createSupplierPayment: vi.fn(),
  createAllocation: vi.fn(),
  createProduct: vi.fn(),
  createSupplier: vi.fn(),
  updateSupplier: vi.fn(),
  uploadFile: vi.fn(),
  previewPurchaseTotals: async () => ({
    subtotal: 100,
    discountTotal: 0,
    taxableTotal: 100,
    cgstTotal: 0,
    sgstTotal: 0,
    igstTotal: 0,
    cessTotal: 0,
    roundOff: 0,
    grandTotal: 100,
    taxTotal: 0,
  }),
  previewSalesTotals: vi.fn(),
}));
vi.mock('@/pages/purchases/usePurchaseOffline', () => ({ usePurchaseOffline: () => undefined }));
vi.mock('@/offline/invoiceDraftCache', () => ({
  loadPurchaseDraft: (...a: unknown[]) => api.loadPurchaseDraft(...a),
  savePurchaseDraft: vi.fn().mockResolvedValue(undefined),
  clearPurchaseDraft: vi.fn().mockResolvedValue(undefined),
  enqueueDraft: (...a: unknown[]) => api.enqueueDraft(...a),
  OUTBOX_WARNING_DISMISS_KEY: 'bizboard.dismiss.outboxPlaintext',
}));

const COMPLETED_BILL = {
  id: 9,
  number: 'PUR-9',
  status: 'COMPLETED',
  purchaseType: 'NON_GST',
  supplier: 3,
  supplierName: 'Mega Suppliers',
  invoiceDate: '2026-10-01',
  priceMode: 'EXCLUSIVE',
  items: [
    { id: 1, product: 7, productName: 'Widget A', quantity: '1', unitPrice: '100', gstRate: '0', cessRate: '0', discountPercent: '0' },
  ],
};

function Landing() {
  const loc = useLocation();
  return <pre data-testid="landing">{JSON.stringify({ path: loc.pathname, state: loc.state })}</pre>;
}

async function openEdit() {
  api.getPurchase.mockResolvedValue(COMPLETED_BILL);
  api.loadPurchaseDraft.mockResolvedValue(null);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/purchases/history/9/edit']}>
        <Routes>
          <Route path="/purchases/history/:id/edit" element={<NewPurchasePage />} />
          <Route path="/purchases/history" element={<Landing />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  await screen.findByText('Widget A');
}

async function clickSave() {
  await waitFor(() => expect(screen.getByRole('button', { name: t('common.save') })).toBeEnabled());
  await userEvent.click(screen.getByRole('button', { name: t('common.save') }));
}

beforeEach(() => {
  api.updatePurchase.mockResolvedValue({ ...COMPLETED_BILL });
});
afterEach(() => {
  registerGlobalConfirm(null);
  vi.clearAllMocks();
});

describe('NewPurchasePage amending a completed bill (WP-7/WP-8)', () => {
  it('asks through the in-app dialog and saves nothing when the owner declines', async () => {
    const ask = vi.fn().mockResolvedValue(false);
    registerGlobalConfirm(ask);
    const native = vi.spyOn(window, 'confirm');
    await openEdit();
    await clickSave();
    await waitFor(() => expect(ask).toHaveBeenCalledTimes(1));
    expect(native).not.toHaveBeenCalled();
    expect(api.updatePurchase).not.toHaveBeenCalled();
    // Declining is a choice, not a failure: no error banner, and the form stays as it was.
    expect(document.querySelector('.MuiAlert-standardError, .MuiAlert-filledError, .MuiAlert-outlinedError')).toBeNull();
    expect(screen.getByText('Widget A')).toBeInTheDocument();
  });

  it('saves with the amend confirmation once the owner agrees', async () => {
    registerGlobalConfirm(vi.fn().mockResolvedValue(true));
    await openEdit();
    await clickSave();
    await waitFor(() => expect(api.updatePurchase).toHaveBeenCalledTimes(1));
    expect(api.updatePurchase.mock.calls[0][0]).toBe(9);
    expect(api.updatePurchase.mock.calls[0][1]).toMatchObject({ confirmAmend: true });
  });
});
