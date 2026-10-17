import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactElement } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { LowStockPage } from '@/pages/inventory/LowStockPage';
import { reorderHref, sortByShortfall, suggestedOrderQty } from '@/pages/inventory/lowStockHelpers';

const listLowStock = vi.hoisted(() => vi.fn());

vi.mock('@/api/resources', () => ({
  listLowStock: () => listLowStock(),
  listReorderLevels: async () => [{ id: 1, productName: 'Soap', warehouseName: 'North', reorderLevel: '12' }],
  listWarehouses: async () => [{ id: 1, name: 'North' }],
  createReorderLevel: vi.fn(),
  listProducts: async () => [],
}));

const auth = vi.hoisted(() => ({ role: 'OWNER' }));
vi.mock('@/auth/AuthContext', () => ({ useAuth: () => ({ user: { id: 1, companyId: 1, role: auth.role } }) }));
vi.mock('@/hooks/useSubscriptionGate', () => ({ useSubscriptionGate: () => ({ writesBlocked: false }) }));
vi.mock('@/hooks/useActiveCustomFieldDefs', () => ({ useVisibleCustomFieldDefs: () => [] }));
vi.mock('@/hooks/useProductSearch', () => ({
  useProductSearch: () => ({
    productQuery: '', setProductQuery: () => undefined, options: [], isFetching: false,
    truncated: false, helperText: undefined, enabled: true, count: 0,
  }),
}));

function wrap(ui: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

const row = (over: Record<string, unknown>) => ({
  product: 1, productName: 'Tea', sku: 'TEA', available: 1, reorderLevel: 5, warehouse: 1, warehouseName: 'Main',
  onHand: 1, reserved: 0, isWarehouseSpecific: true, ...over,
});

describe('LowStockPage', () => {
  it('keeps the per-godown reorder rules on this page, where they take effect', async () => {
    listLowStock.mockResolvedValueOnce([]);
    wrap(<LowStockPage />);
    expect(await screen.findByText('Per-godown reorder')).toBeTruthy();
    expect(screen.getByRole('button', { name: /godown reorder/i })).toBeTruthy();
  });

  it('hides the reorder rules from someone who cannot change them', async () => {
    auth.role = 'SALES_STAFF';
    listLowStock.mockResolvedValueOnce([row({})]);
    try {
      wrap(<LowStockPage />);
      expect(await screen.findByText('Tea')).toBeTruthy();
      expect(screen.queryByText('Per-godown reorder')).toBeNull();
      expect(screen.queryByRole('button', { name: /godown reorder/i })).toBeNull();
    } finally {
      auth.role = 'OWNER';
    }
  });

  it('says the shop is well stocked when nothing is below reorder', async () => {
    listLowStock.mockResolvedValueOnce([]);
    wrap(<LowStockPage />);
    expect(await screen.findByText('All items are well stocked above reorder levels.')).toBeTruthy();
  });

  it('names the available and reorder columns in plain language', async () => {
    listLowStock.mockResolvedValueOnce([row({})]);
    wrap(<LowStockPage />);
    expect(await screen.findByText('Tea')).toBeTruthy();
    expect(screen.getByText('Available')).toBeTruthy();
    expect(screen.getByText('Reorder Level')).toBeTruthy();
    expect(screen.getByText('At or below reorder')).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Plan purchases for all of these' }).getAttribute('href')).toBe('/inventory/purchase-planning?select=all');
  });

  it('shows which godown a row is about, and "All godowns" for a company-wide total', async () => {
    listLowStock.mockResolvedValueOnce([
      row({ product: 1, productName: 'Tea', warehouseName: 'North', isWarehouseSpecific: true }),
      row({ product: 2, productName: 'Rice', sku: 'RICE', warehouseName: 'Main', isWarehouseSpecific: false }),
    ]);
    wrap(<LowStockPage />);
    expect(await screen.findByText('North')).toBeTruthy();
    expect(screen.getByText('All godowns')).toBeTruthy();
    // The company-wide row must not claim it belongs to the one godown the API happened to pick.
    expect(screen.queryByText('Main')).toBeNull();
  });

  it('sends Order / Buy to the purchase-order editor with the item and a suggested quantity', async () => {
    listLowStock.mockResolvedValueOnce([row({ product: 7, available: 2, reorderLevel: 10 })]);
    wrap(<LowStockPage />);
    const link = await screen.findByRole('link', { name: /Order 8 of Tea/ });
    expect(link.getAttribute('href')).toBe('/purchases/orders/new?product=7&qty=8');
  });

  it('puts the biggest shortfall first and filters by name or SKU', async () => {
    listLowStock.mockResolvedValueOnce([
      row({ product: 1, productName: 'Tea', sku: 'TEA', available: 4, reorderLevel: 5 }),
      row({ product: 2, productName: 'Rice', sku: 'RICE-5', available: 0, reorderLevel: 20 }),
    ]);
    const user = userEvent.setup();
    wrap(<LowStockPage />);
    await screen.findByText('Rice');
    const names = screen.getAllByRole('row').slice(1).map((r) => r.textContent ?? '');
    expect(names[0]).toContain('Rice');
    await user.type(screen.getByLabelText('Search items'), 'tea');
    expect(screen.queryByText('Rice')).toBeNull();
    expect(screen.getByText('Tea')).toBeTruthy();
    await user.clear(screen.getByLabelText('Search items'));
    await user.type(screen.getByLabelText('Search items'), 'zzz');
    expect(await screen.findByText('No low-stock item matches your search.')).toBeTruthy();
  });
});

describe('LowStockPage tabs', () => {
  it('keeps out-of-stock items with no reorder rule apart from low stock', async () => {
    listLowStock.mockResolvedValueOnce([
      row({ product: 1, productName: 'Tea', hasReorderRule: true }),
      row({ product: 2, productName: 'Old stock', sku: 'OLD', available: 0, reorderLevel: 0, hasReorderRule: false }),
    ]);
    const user = userEvent.setup();
    wrap(<LowStockPage />);
    expect(await screen.findByText('Tea')).toBeTruthy();
    expect(screen.queryByText('Old stock')).toBeNull();
    expect(screen.getByRole('tab', { name: 'Low stock (1)' })).toBeTruthy();
    await user.click(screen.getByRole('tab', { name: 'Out of stock (1)' }));
    expect(await screen.findByText('Old stock')).toBeTruthy();
    expect(screen.queryByText('Tea')).toBeNull();
    expect(screen.getByText(/no reorder level and nothing left/)).toBeTruthy();
  });

  it('asks for both lists in one request', async () => {
    listLowStock.mockClear();
    listLowStock.mockResolvedValueOnce([row({})]);
    wrap(<LowStockPage />);
    await screen.findByText('Tea');
    expect(listLowStock).toHaveBeenCalledTimes(1);
  });
});

describe('lowStockHelpers', () => {
  it('suggests at least one unit and keeps fractions', () => {
    expect(suggestedOrderQty({ available: 5, reorderLevel: 5 })).toBe(1);
    expect(suggestedOrderQty({ available: '1.25', reorderLevel: '3' })).toBe(1.75);
  });
  it('builds the editor link', () => {
    expect(reorderHref({ product: 3, available: 0, reorderLevel: 4 })).toBe('/purchases/orders/new?product=3&qty=4');
  });
  it('orders by shortfall, then name', () => {
    const rows = sortByShortfall([
      { productName: 'B', sku: '', available: 0, reorderLevel: 2 },
      { productName: 'A', sku: '', available: 0, reorderLevel: 2 },
      { productName: 'C', sku: '', available: 0, reorderLevel: 9 },
    ] as never[]);
    expect(rows.map((r: { productName: string }) => r.productName)).toEqual(['C', 'A', 'B']);
  });
});

describe('LowStockPage tab behaviour and wording', () => {
  it('is a real tablist: one tab stop, arrow keys switch tabs, the panel is named by the tab', async () => {
    listLowStock.mockResolvedValue([row({}), row({ product: 2, productName: 'Salt', hasReorderRule: false, reorderLevel: 0 })]);
    const user = userEvent.setup();
    wrap(<LowStockPage />);
    const low = await screen.findByRole('tab', { name: 'Low stock (1)' });
    const out = screen.getByRole('tab', { name: 'Out of stock (1)' });
    expect(low.getAttribute('aria-selected')).toBe('true');
    expect(low.getAttribute('tabindex')).toBe('0');
    expect(out.getAttribute('tabindex')).toBe('-1');
    low.focus();
    await user.keyboard('{ArrowRight}');
    expect(out.getAttribute('aria-selected')).toBe('true');
    expect(document.activeElement).toBe(out);
    expect(screen.getByRole('tabpanel').getAttribute('aria-labelledby')).toBe(out.id);
    await user.keyboard('{Home}');
    expect(low.getAttribute('aria-selected')).toBe('true');
  });

  it('does not call an item with no reorder rule "at or below reorder"', async () => {
    listLowStock.mockResolvedValue([row({ product: 2, productName: 'Salt', hasReorderRule: false, reorderLevel: 0 })]);
    const user = userEvent.setup();
    wrap(<LowStockPage />);
    await user.click(await screen.findByRole('tab', { name: 'Out of stock (1)' }));
    expect(await screen.findByText('Out of stock (no reorder rule)')).toBeTruthy();
    expect(screen.queryByText('At or below reorder')).toBeNull();
  });
});
