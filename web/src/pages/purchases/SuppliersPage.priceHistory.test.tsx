import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import userEvent from '@testing-library/user-event';
import type { ReactElement } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { SuppliersPage } from '@/pages/purchases/SuppliersPage';
import { t } from '@/i18n';

vi.mock('@/config/featureFlags', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/config/featureFlags')>();
  return {
    ...actual,
    isRuntimeFlagEnabled: (key: string) =>
      Boolean((globalThis as { __ff?: Record<string, boolean> }).__ff?.[key]),
    useFeatureFlagEpoch: () => 0,
  };
});

const PRODUCT_OPTION = { id: 7, name: 'Widget A', sku: 'WID-A' };

vi.mock('@/hooks/useProductSearch', () => ({
  useProductSearch: () => ({
    productQuery: '',
    setProductQuery: () => undefined,
    options: [PRODUCT_OPTION],
    isFetching: false,
    truncated: false,
    helperText: undefined,
    enabled: true,
    count: 1,
  }),
}));

const getSupplierPriceHistory = vi.fn();

vi.mock('@/api/resources', () => ({
  listSuppliers: async () => [{
    id: 3,
    name: 'Mega Suppliers',
    phone: '9999999999',
    gstin: '',
    state: 'Karnataka',
    isActive: true,
  }],
  getCompany: async () => ({ id: 1, name: 'Shop', isGstRegistered: false }),
  createSupplier: vi.fn(),
  updateSupplier: vi.fn(),
  verifySupplierGstin: vi.fn(),
  getSupplierPriceHistory: (...args: unknown[]) => getSupplierPriceHistory(...args),
}));

function wrap(ui: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

async function openDialogAndSelectProduct() {
  await userEvent.click(await screen.findByRole('button', { name: 'Price history' }));
  await screen.findByRole('heading', { name: /Price history — Mega Suppliers/ });
  const input = screen.getByLabelText('Product');
  await userEvent.type(input, 'Widget');
  await userEvent.click(await screen.findByText('Widget A'));
}

describe('SuppliersPage price history', () => {
  beforeEach(() => {
    (globalThis as { __ff?: Record<string, boolean> }).__ff = {};
    getSupplierPriceHistory.mockReset();
  });

  it('hides the price-history action when the flag is off', async () => {
    wrap(<SuppliersPage />);
    expect(await screen.findByText('Mega Suppliers')).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Price history' })).toBeNull();
  });

  it('opens the price-history dialog when the flag is on', async () => {
    (globalThis as { __ff?: Record<string, boolean> }).__ff = { ENABLE_SUPPLIER_PRICE_HISTORY: true };
    getSupplierPriceHistory.mockResolvedValue({ rows: [] });
    wrap(<SuppliersPage />);
    await userEvent.click(await screen.findByRole('button', { name: 'Price history' }));
    expect(await screen.findByRole('heading', { name: /Price history — Mega Suppliers/ })).toBeTruthy();
  });

  it('renders real row data in date/source/qty/price columns, and no score/rank/reliability UI element', async () => {
    (globalThis as { __ff?: Record<string, boolean> }).__ff = { ENABLE_SUPPLIER_PRICE_HISTORY: true };
    getSupplierPriceHistory.mockResolvedValue({
      supplierId: 3,
      productId: 7,
      rows: [
        { source: 'PURCHASE_INVOICE', documentId: 1, documentNumber: 'PI-1', documentDate: '2026-01-01', quantity: '2', unitPrice: '10.00' },
        { source: 'PURCHASE_ORDER', documentId: 2, documentNumber: 'PO-1', documentDate: '2026-01-15', quantity: '3', unitPrice: '12.00' },
      ],
    });
    wrap(<SuppliersPage />);
    await openDialogAndSelectProduct();

    expect(await screen.findByText('2026-01-01')).toBeTruthy();
    expect(screen.getByText(/PI-1/)).toBeTruthy();
    expect(screen.getByText('2026-01-15')).toBeTruthy();
    expect(screen.getByText(/PO-1/)).toBeTruthy();

    // Exactly the four documented columns — no fifth score/rank column.
    const headerCells = screen.getAllByRole('columnheader');
    expect(headerCells).toHaveLength(4);

    expect(screen.queryByText(/score/i)).toBeNull();
    expect(screen.queryByText(/rank/i)).toBeNull();
    expect(screen.queryByText(/reliab/i)).toBeNull();
  });

  it('renders the empty-history message when the API resolves with no rows', async () => {
    (globalThis as { __ff?: Record<string, boolean> }).__ff = { ENABLE_SUPPLIER_PRICE_HISTORY: true };
    getSupplierPriceHistory.mockResolvedValue({ rows: [] });
    wrap(<SuppliersPage />);
    await openDialogAndSelectProduct();
    expect(await screen.findByText(t('supplierPrices.empty'))).toBeTruthy();
  });
});
