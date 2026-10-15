import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { configure, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AxiosError } from 'axios';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { NewPurchasePage } from '@/pages/purchases/NewPurchasePage';
import { t } from '@/i18n';
import type { DraftLine } from '@/components/billing';

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
  createPurchase: vi.fn(),
  completePurchase: vi.fn(),
  createSupplierPayment: vi.fn(),
  createAllocation: vi.fn(),
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
  getPurchase: vi.fn(),
  createPurchase: (...a: unknown[]) => api.createPurchase(...a),
  updatePurchase: vi.fn(),
  completePurchase: (...a: unknown[]) => api.completePurchase(...a),
  createSupplierPayment: (...a: unknown[]) => api.createSupplierPayment(...a),
  createAllocation: (...a: unknown[]) => api.createAllocation(...a),
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

const LINE: DraftLine = {
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
  unitPrice: 100,
  discountPercent: 0,
  discountAmount: 0,
  gstRate: 0,
  cessRate: 0,
  taxableAmount: 100,
  cgst: 0,
  sgst: 0,
  igst: 0,
  cess: 0,
  lineTotal: 100,
  gross: 100,
};

function Landing() {
  const loc = useLocation();
  return <pre data-testid="landing">{JSON.stringify({ path: loc.pathname, state: loc.state })}</pre>;
}

async function openWithDraft() {
  api.loadPurchaseDraft.mockResolvedValue({
    savedAt: new Date().toISOString(),
    payload: { supplierId: 3, purchaseType: 'NON_GST', lines: [LINE] },
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/purchases/new']}>
        <Routes>
          <Route path="/purchases/new" element={<NewPurchasePage />} />
          <Route path="/purchases/history" element={<Landing />} />
          <Route path="/purchases/history/:id" element={<Landing />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  await userEvent.click(await screen.findByRole('button', { name: t('billing.restoreDraft') }));
  await screen.findByText('Widget A');
}

const landing = () => JSON.parse(screen.getByTestId('landing').textContent ?? '{}') as {
  path: string;
  state?: { message?: string; paymentRetry?: { payNow: { amount: number; mode: string }; message: string } };
};

async function saveAndComplete() {
  // Completing waits for the server's totals preview, so the button enables a moment after the lines appear.
  try {
    await waitFor(() =>
      expect(screen.getByRole('button', { name: t('billing.saveAndComplete') })).toBeEnabled(),
    );
  } catch (err) {
    const why = document.getElementById('complete-disabled-reason')?.textContent;
    throw new Error(`Save & Complete stayed disabled: ${why ?? 'no reason shown'} :: ${(err as Error).message.slice(0, 50)}`);
  }
  await userEvent.click(screen.getByRole('button', { name: t('billing.saveAndComplete') }));
}

beforeEach(() => {
  api.createPurchase.mockResolvedValue({ id: 1, status: 'DRAFT' });
  api.completePurchase.mockResolvedValue({ id: 1, number: 'PUR-1', status: 'COMPLETED', paid: '40.00' });
});
afterEach(() => vi.clearAllMocks());

describe('NewPurchasePage Save & Complete with a payment (WP-1)', () => {
  it('sends the payment inside the Complete request and never creates payment and allocation itself', async () => {
    await openWithDraft();
    await userEvent.type(screen.getByRole('textbox', { name: t('billing.amountPaid') }), '40');
    await saveAndComplete();
    await waitFor(() => expect(api.completePurchase).toHaveBeenCalledTimes(1));
    const [id, extra] = api.completePurchase.mock.calls[0];
    expect(id).toBe(1);
    expect(extra.payNow).toMatchObject({ amount: 40, mode: 'CASH' });
    expect(extra.idempotencyKey).toMatch(/-complete$/);
    expect(api.createSupplierPayment).not.toHaveBeenCalled();
    expect(api.createAllocation).not.toHaveBeenCalled();
    await waitFor(() => expect(landing().path).toBe('/purchases/history'));
  });

  it('sends no payment when nothing was paid', async () => {
    await openWithDraft();
    await saveAndComplete();
    await waitFor(() => expect(api.completePurchase).toHaveBeenCalledTimes(1));
    expect(api.completePurchase.mock.calls[0][1].payNow).toBeUndefined();
  });

  it('hands a refused payment to the bill page with a retry instead of a vanishing flash', async () => {
    api.completePurchase.mockResolvedValue({
      id: 1,
      number: 'PUR-1',
      status: 'COMPLETED',
      payment: null,
      paymentError: { code: 'business_rule_violation', message: 'Supplier GSTIN is cancelled.' },
    });
    await openWithDraft();
    await userEvent.type(screen.getByRole('textbox', { name: t('billing.amountPaid') }), '40');
    await saveAndComplete();
    await waitFor(() => expect(landing().path).toBe('/purchases/history/1'));
    expect(landing().state?.paymentRetry).toMatchObject({
      payNow: { amount: 40, mode: 'CASH' },
      message: 'Supplier GSTIN is cancelled.',
    });
  });

  it('keeps the completion notices with the saved message', async () => {
    api.completePurchase.mockResolvedValue({
      id: 1,
      number: 'PUR-1',
      status: 'COMPLETED',
      warnings: ['Supplier bill number already used on PUR-0002.'],
    });
    await openWithDraft();
    await saveAndComplete();
    await waitFor(() => expect(landing().path).toBe('/purchases/history'));
    expect(landing().state?.message).toContain('already used on PUR-0002');
  });
});

describe('NewPurchasePage "mark as fully paid" (WP-11)', () => {
  it('pays the whole total without writing state during render, and gives the typed amount back when unticked', async () => {
    await openWithDraft();
    const amount = screen.getByRole('textbox', { name: t('billing.amountPaid') }) as HTMLInputElement;
    await userEvent.type(amount, '25');
    await userEvent.click(screen.getByRole('checkbox', { name: t('billing.markFullyPaid') }));
    await waitFor(() => expect(amount.value).toBe('100'));
    await saveAndComplete();
    await waitFor(() => expect(api.completePurchase).toHaveBeenCalledTimes(1));
    expect(api.completePurchase.mock.calls[0][1].payNow.amount).toBe(100);
  });

  it('unticking keeps what was typed before', async () => {
    await openWithDraft();
    const amount = screen.getByRole('textbox', { name: t('billing.amountPaid') }) as HTMLInputElement;
    await userEvent.type(amount, '25');
    const box = screen.getByRole('checkbox', { name: t('billing.markFullyPaid') });
    await userEvent.click(box);
    await waitFor(() => expect(amount.value).toBe('100'));
    await userEvent.click(box);
    await waitFor(() => expect(amount.value).toBe('25'));
  });
});

describe('NewPurchasePage offline (WP-7)', () => {
  it('queues the bill and reports it as saved on this device, not as an error', async () => {
    api.createPurchase.mockRejectedValue(new AxiosError('Network Error', 'ERR_NETWORK'));
    await openWithDraft();
    await saveAndComplete();
    await waitFor(() => expect(api.enqueueDraft).toHaveBeenCalledTimes(1));
    expect((await screen.findAllByText(t('billing.savedOffline'))).length).toBeGreaterThan(0);
    expect(document.querySelector('.MuiAlert-standardError, .MuiAlert-filledError, .MuiAlert-outlinedError')).toBeNull();
    // The form is reset so a second click cannot queue the same bill again under a new key.
    await waitFor(() => expect(screen.queryByText('Widget A')).not.toBeInTheDocument());
    expect(api.createPurchase).toHaveBeenCalledTimes(1);
  });

  it('shows a real server error as an error and does not queue it', async () => {
    api.createPurchase.mockRejectedValue(new Error('Supplier is required.'));
    await openWithDraft();
    await saveAndComplete();
    expect(await screen.findByText(/supplier is required/i)).toBeInTheDocument();
    expect(api.enqueueDraft).not.toHaveBeenCalled();
  });
});
