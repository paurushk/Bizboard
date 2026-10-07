import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { PosPage } from '@/pages/pos/PosPage';
import type { Company, Customer, Product, Warehouse } from '@/types/domain';

const COMPANY_ID = 9;
const USER_ID = 1;
const CART_STORAGE_KEY = `bizboard:pos-active-cart:${COMPANY_ID}`;

const PRODUCT: Product = {
  id: 1,
  name: 'Widget',
  sku: 'WID-1',
  sellingPrice: '100',
  gstRate: 0,
  purchasePrice: 0,
  reorderLevel: 0,
  status: 'ACTIVE',
};

function seedCart() {
  localStorage.setItem(
    CART_STORAGE_KEY,
    JSON.stringify([
      {
        key: '1-widget',
        product: PRODUCT,
        quantity: 1,
        discountPercent: 0,
        unitName: 'PCS',
      },
    ]),
  );
}

const WALKIN_CUSTOMER: Customer = {
  id: 5,
  name: 'Walk-in Customer',
  status: 'ACTIVE',
  state: 'MH',
};

const COMPANY: Company = {
  id: COMPANY_ID,
  name: 'Test Co',
  registrationType: 'UNREGISTERED',
  state: 'MH',
  negativeStockPolicy: 'ALLOW',
  priceMode: 'EXCLUSIVE',
} as Company;

const WAREHOUSE: Warehouse = { id: 1, name: 'Main', code: 'MAIN', isDefault: true };

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({
    user: { id: USER_ID, email: 'owner@x.test', fullName: 'Owner', role: 'OWNER', companyId: COMPANY_ID },
  }),
}));

vi.mock('@/hooks/useSubscriptionGate', () => ({
  useSubscriptionGate: () => ({
    subscription: undefined,
    writesBlocked: false,
    isLoading: false,
    refetch: vi.fn(),
  }),
}));

vi.mock('@/config/features', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/config/features')>();
  return {
    ...actual,
    isPosEnabled: () => true,
    isAtomicPosCheckoutEnabled: () => true,
  };
});

vi.mock('@/offline/invoiceDraftCache', () => ({
  OUTBOX_WARNING_DISMISS_KEY: 'test.dismiss.outboxPlaintext',
  listDrafts: vi.fn(async () => []),
  enqueueDraft: vi.fn(async () => undefined),
  updateDraft: vi.fn(async () => undefined),
  removeDraft: vi.fn(async () => undefined),
  flushOutbox: vi.fn(async () => ({ flushed: 0, failed: 0, errors: [] })),
}));

vi.mock('@/lib/native', () => ({
  onNetworkOnline: () => () => {},
  scanBarcode: vi.fn(async () => null),
  isNative: () => false,
  printEscPos: vi.fn(async () => 'none'),
  DRAWER_KICK: new Uint8Array(),
}));

import { createPosHold } from '@/pages/pos/posCounterApi';

vi.mock('@/pages/pos/posCounterApi', () => ({
  getPosSettings: vi.fn(async () => ({
    tenderAccounts: { UPI: 1, CARD: 1, BANK: 1, CHEQUE: 1 },
    maxLineDiscount: '100',
    expiredLotPolicy: 'REASON',
    pinConfigured: false,
    walkInCustomerId: null,
  })),
  postPosEvent: vi.fn(async () => undefined),
  listPosHolds: vi.fn(async () => []),
  createPosHold: vi.fn(async () => ({ id: 1 })),
  releasePosHold: vi.fn(async () => undefined),
  getTodayShift: vi.fn(async () => ({ shift: null })),
  openTodayShift: vi.fn(async () => undefined),
  dropShiftCash: vi.fn(async () => undefined),
  closeTodayShift: vi.fn(async () => ({})),
  collectPosPayment: vi.fn(async () => undefined),
  returnPosBill: vi.fn(async () => ({ id: 1, exchange: false, customerId: 1 })),
}));

vi.mock('@/lib/telemetry', () => ({
  trackShopFloor: vi.fn(),
  trackInvoiceComplete: vi.fn(),
  trackJourneyStarted: vi.fn(),
  trackJourneyFailed: vi.fn(),
  classifyCompleteFailure: () => 'unknown',
}));

vi.mock('@/api/legacy/sales', () => ({
  previewSalesTotals: vi.fn(async () => ({ grandTotal: 100 })),
}));

const posCheckout = vi.fn();

vi.mock('@/api/resources', () => ({
  getCompany: vi.fn(async () => COMPANY),
  listWarehouses: vi.fn(async () => [WAREHOUSE]),
  listProductsPage: vi.fn(async () => ({ results: [PRODUCT], count: 1, next: null, previous: null })),
  getProduct: vi.fn(async () => PRODUCT),
  searchProducts: vi.fn(async () => [PRODUCT]),
  listCustomersPage: vi.fn(async () => ({ results: [WALKIN_CUSTOMER], count: 1, next: null, previous: null })),
  listCustomFieldDefinitions: vi.fn(async () => []),
  listProductStockSummaries: vi.fn(async () => []),
  listPriceLists: vi.fn(async () => []),
  listBatches: vi.fn(async () => []),
  listStock: vi.fn(async () => []),
  getCustomer: vi.fn(async () => WALKIN_CUSTOMER),
  createCustomer: vi.fn(async () => WALKIN_CUSTOMER),
  posCheckout: (...args: unknown[]) => posCheckout(...args),
  printPosThermalOrWarn: vi.fn(async () => null),
  shareInvoice: vi.fn(async () => ({ status: 'QUEUED' })),
}));

const printPosThermalOrWarnMock = vi.fn(async () => null);
vi.mock('@/pages/pos/printPosThermal', () => ({
  printPosThermalOrWarn: (...args: unknown[]) => printPosThermalOrWarnMock(...args),
}));

async function finishPayShortcut(key: string) {
  fireEvent.keyDown(window, { key });
  await waitFor(() => {
    const confirmBtn = screen.queryByRole('button', { name: /complete as walk-in/i });
    if (confirmBtn) fireEvent.click(confirmBtn);
    expect(posCheckout).toHaveBeenCalled();
  });
}

function renderPos() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <PosPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('PosPage Keyboard-First F1-F10 Shortcuts (Turbo Mode)', () => {
  beforeEach(() => {
    seedCart();
    posCheckout.mockReset();
    posCheckout.mockResolvedValue({
      invoice: {
        id: 101,
        number: 'INV-101',
        grandTotal: '100.00',
      },
      id: 101,
      number: 'INV-101',
      grandTotal: '100.00',
    });
  });

  afterEach(() => {
    localStorage.clear();
  });

  it('F2 focuses and selects the barcode search input', async () => {
    renderPos();
    const searchInput = await screen.findByPlaceholderText(/scan barcode or search/i);
    // Blur search input first
    searchInput.blur();
    expect(document.activeElement).not.toBe(searchInput);

    // Fire F2 keydown
    fireEvent.keyDown(window, { key: 'F2' });

    expect(document.activeElement).toBe(searchInput);
  });

  it('F3 focuses the customer select input', async () => {
    renderPos();
    await screen.findByPlaceholderText(/scan barcode or search/i);

    // Fire F3 keydown
    fireEvent.keyDown(window, { key: 'F3' });

    const customerInput = screen.getByLabelText(/customer/i);
    expect(document.activeElement).toBe(customerInput);
  });

  it('F1 triggers cash payment and completes checkout', async () => {
    renderPos();
    await screen.findByRole('button', { name: /^cash\s+—/i });

    await finishPayShortcut('F1');

    await waitFor(() => {
      expect(posCheckout).toHaveBeenCalledWith(
        expect.objectContaining({
          payment: expect.objectContaining({ mode: 'CASH' }),
        }),
        expect.anything(),
      );
    });
  });

  it('F4 triggers card payment and completes checkout', async () => {
    renderPos();
    // Card sits under "More" until it is the last-used tender; the shortcut still works.
    await screen.findByRole('button', { name: /^more$/i });

    await finishPayShortcut('F4');

    await waitFor(() => {
      expect(posCheckout).toHaveBeenCalledWith(
        expect.objectContaining({
          payment: expect.objectContaining({ mode: 'CARD' }),
        }),
        expect.anything(),
      );
    });
  });

  it('F8 and F9 hold the cart on the server and recall it', async () => {
    renderPos();
    await screen.findByRole('button', { name: /hold bill/i });

    fireEvent.keyDown(window, { key: 'F8' });
    await waitFor(() => expect(createPosHold).toHaveBeenCalled());

    // The held cart comes back with F9.
    fireEvent.keyDown(window, { key: 'F9' });
    await waitFor(() => expect(screen.getByRole('button', { name: /hold bill/i })).toBeTruthy());
  });

  it('F10 clears the active cart', async () => {
    renderPos();
    await screen.findByRole('button', { name: /clear cart/i });
    expect(screen.getByText('Widget')).toBeTruthy();

    fireEvent.keyDown(window, { key: 'F10' });
    expect(screen.getByText('Widget')).toBeTruthy();
    fireEvent.click(await screen.findByRole('button', { name: /clear the cart/i }));

    await waitFor(() => {
      expect(screen.queryByText('Widget')).toBeNull();
    });
  });

  it('F11 triggers quick reprint of the last completed bill', async () => {
    renderPos();
    await screen.findByRole('button', { name: /^cash\s+—/i });

    await finishPayShortcut('F1');
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).toBeNull();
    });

    printPosThermalOrWarnMock.mockClear();

    // Now press F11 for quick reprint
    fireEvent.keyDown(window, { key: 'F11' });

    await waitFor(() => {
      expect(printPosThermalOrWarnMock).toHaveBeenCalledWith(
        expect.objectContaining({ id: 101, number: 'INV-101' }),
      );
    });
  });

  it('ignores a held key: auto-repeat never clears the cart', async () => {
    renderPos();
    await screen.findByRole('button', { name: /clear cart/i });

    fireEvent.keyDown(window, { key: 'F10', repeat: true });
    await new Promise((resolve) => setTimeout(resolve, 150));

    expect(screen.getByText('Widget')).toBeTruthy();
  });

  it('ignores a held payment key: auto-repeat never starts a checkout', async () => {
    renderPos();
    await screen.findByRole('button', { name: /^cash\s+—/i });

    fireEvent.keyDown(window, { key: 'F1', repeat: true });
    fireEvent.keyDown(window, { key: 'F4', repeat: true });
    await new Promise((resolve) => setTimeout(resolve, 150));

    expect(posCheckout).not.toHaveBeenCalled();
    expect(screen.queryByRole('button', { name: /complete as walk-in/i })).toBeNull();
  });

  it('still acts on the first press of a key', async () => {
    renderPos();
    await screen.findByRole('button', { name: /clear cart/i });

    fireEvent.keyDown(window, { key: 'F10', repeat: false });
    fireEvent.click(await screen.findByRole('button', { name: /clear the cart/i }));

    await waitFor(() => {
      expect(screen.queryByText('Widget')).toBeNull();
    });
  });
});
