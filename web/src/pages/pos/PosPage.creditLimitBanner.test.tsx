import { AxiosError } from 'axios';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { PosPage } from '@/pages/pos/PosPage';
import type { Company, Customer, Warehouse } from '@/types/domain';

// BB — dedicated credit-limit-exceeded banner on the POS checkout screen
// (state `creditLimitBanner`, set by `handleCheckoutError` when
// getErrorCode(err) === 'credit_limit_exceeded'). There was previously no
// component test at all for PosPage.tsx; this file adds focused coverage
// for just that banner, not the whole POS surface.

const COMPANY_ID = 9;
const USER_ID = 1;
const CART_STORAGE_KEY = `bizboard:pos-active-cart:${COMPANY_ID}`;

function seedCart() {
  localStorage.setItem(
    CART_STORAGE_KEY,
    JSON.stringify([
      {
        key: '1-widget',
        product: {
          id: 1,
          name: 'Widget',
          sku: 'WID-1',
          sellingPrice: '100',
          gstRate: 0,
          purchasePrice: 0,
          reorderLevel: 0,
          status: 'ACTIVE',
        },
        quantity: 1,
        discountPercent: 0,
        unitName: 'PCS',
      },
    ]),
  );
}

function makeCreditLimitError(details?: Record<string, string>) {
  return new AxiosError(
    'Request failed with status code 400',
    'ERR_BAD_REQUEST',
    undefined,
    undefined,
    {
      status: 400,
      data: {
        error: {
          code: 'credit_limit_exceeded',
          message: 'Credit limit exceeded',
          ...(details ? { details } : {}),
        },
      },
    } as never,
  );
}

function makeGenericError() {
  return new AxiosError(
    'Request failed with status code 400',
    'ERR_BAD_REQUEST',
    undefined,
    undefined,
    {
      status: 400,
      data: {
        error: {
          code: 'invalid_amount',
          message: 'The tendered amount is invalid.',
        },
      },
    } as never,
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
  listCustomersPage: vi.fn(async () => ({
    results: [WALKIN_CUSTOMER],
    count: 1,
    next: null,
    previous: null,
  })),
  getCustomer: vi.fn(async () => WALKIN_CUSTOMER),
  listPriceLists: vi.fn(async () => []),
  listStock: vi.fn(async () => []),
  listWarehouses: vi.fn(async () => [WAREHOUSE]),
  posCheckout: (...args: unknown[]) => posCheckout(...args),
  searchProducts: vi.fn(async () => []),
  createReceipt: vi.fn(),
  createAllocation: vi.fn(),
  createSalesInvoice: vi.fn(),
  completeSalesInvoice: vi.fn(),
  getSalesInvoice: vi.fn(),
  deleteSalesInvoice: vi.fn(),
  getUpiQr: vi.fn(),
  createCustomer: vi.fn(),
  shareInvoice: vi.fn(),
  downloadInvoiceThermalPdf: vi.fn(),
}));

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <PosPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

async function clickCashPay(user: ReturnType<typeof userEvent.setup>) {
  const cashButton = await screen.findByRole('button', { name: /^cash\s+—/i });
  await waitFor(() => expect(cashButton).not.toBeDisabled());
  await user.click(cashButton);
}

describe('PosPage credit-limit banner', () => {
  beforeEach(() => {
    localStorage.clear();
    seedCart();
    posCheckout.mockReset();
  });

  afterEach(() => {
    localStorage.clear();
  });

  it('shows the dedicated banner with customer name and figures when details are present', async () => {
    posCheckout.mockRejectedValueOnce(
      makeCreditLimitError({
        customer_name: 'Alice Traders',
        credit_limit: '5,000.00',
        current_exposure: '4,800.00',
        invoice_total: '500.00',
      }),
    );
    const user = userEvent.setup();
    wrap();

    await clickCashPay(user);

    expect(await screen.findByText('Credit limit exceeded')).toBeTruthy();
    expect(
      await screen.findByText('Alice Traders has exceeded their credit limit.'),
    ).toBeTruthy();
    expect(
      await screen.findByText('Limit ₹5,000.00 · already owes ₹4,800.00 · this sale ₹500.00'),
    ).toBeTruthy();
  });

  it('falls back to a generic message when the error has no detail numbers', async () => {
    posCheckout.mockRejectedValueOnce(makeCreditLimitError());
    const user = userEvent.setup();
    wrap();

    await clickCashPay(user);

    expect(await screen.findByText('Credit limit exceeded')).toBeTruthy();
    expect(
      await screen.findByText('This customer has exceeded their credit limit.'),
    ).toBeTruthy();
    // No numbers line when credit_limit/current_exposure/invoice_total are absent.
    expect(screen.queryByText(/^Limit ₹/)).toBeNull();
  });

  it('does not show the credit-limit banner for a different error code', async () => {
    posCheckout.mockRejectedValueOnce(makeGenericError());
    const user = userEvent.setup();
    wrap();

    await clickCashPay(user);

    // The generic error path handles it instead.
    expect(await screen.findByText('The tendered amount is invalid.')).toBeTruthy();
    expect(screen.queryByText('Credit limit exceeded')).toBeNull();
    expect(
      screen.queryByText('This customer has exceeded their credit limit.'),
    ).toBeNull();
  });

  it('shows only the dedicated banner, not the generic error toast, for the same failure', async () => {
    posCheckout.mockRejectedValueOnce(
      makeCreditLimitError({
        customer_name: 'Alice Traders',
        credit_limit: '5,000.00',
        current_exposure: '4,800.00',
        invoice_total: '500.00',
      }),
    );
    const user = userEvent.setup();
    wrap();

    await clickCashPay(user);

    expect(await screen.findByText('Credit limit exceeded')).toBeTruthy();
    // Regression guard: the generic error alert must not also surface the
    // same failure (e.g. as a raw "field: value" dump of the same details).
    expect(screen.queryByText(/customer_name:/i)).toBeNull();
    expect(screen.queryByText(/credit_limit:/i)).toBeNull();
  });
});
