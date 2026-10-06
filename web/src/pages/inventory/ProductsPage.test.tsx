import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ProductsPage } from '@/pages/inventory/ProductsPage';

const listProductsPage = vi.hoisted(() => vi.fn());
const listProducts = vi.hoisted(() => vi.fn());
const listStock = vi.hoisted(() => vi.fn());

vi.mock('@/api/resources', () => ({
  deleteProduct: vi.fn(),
  listProducts: (...args: unknown[]) => listProducts(...args),
  listProductsPage: (...args: unknown[]) => listProductsPage(...args),
  listStock: (...args: unknown[]) => listStock(...args),
}));

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ user: { id: 1, companyId: 1, role: 'OWNER', canAdjustInventory: true, company: {} } }),
}));

// jsdom has no layout, so a windowed table renders no rows: render them all.
vi.mock('@/components/VirtualizedTable', () => ({
  VirtualizedTable: ({ children, rowCount }: { children: (a: unknown) => unknown; rowCount: number }) =>
    children({
      rows: Array.from({ length: rowCount }, (_, i) => ({ index: i, start: i * 52, end: (i + 1) * 52, size: 52, key: i })),
      totalSize: rowCount * 52,
      measureElement: () => undefined,
    }),
}));
vi.mock('@/pages/inventory/ItemFormDialog', () => ({ ItemFormDialog: () => null }));
vi.mock('@/hooks/useActiveCustomFieldDefs', () => ({ useVisibleCustomFieldDefs: () => [] }));

const product = (id: number, name: string, categoryName: string) => ({
  id, name, sku: `SKU-${id}`, status: 'ACTIVE', sellingPrice: '10', gstRate: '18', reorderLevel: '1',
  categoryName, brandName: '', unitName: 'PCS', customFields: {},
});

function wrap() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ProductsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('ProductsPage filters', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Page one holds only "Soap"; "Tea" lives on a later page of the catalogue.
    listProductsPage.mockResolvedValue({ count: 2, next: 'page2', previous: null, results: [product(1, 'Soap', 'Home')] });
    listProducts.mockResolvedValue([product(1, 'Soap', 'Home'), product(2, 'Tea', 'Grocery')]);
    listStock.mockResolvedValue([]);
  });

  it('a category filter matches items on every page, not only the page on screen', async () => {
    const user = userEvent.setup();
    wrap();
    expect(await screen.findByText('Soap')).toBeTruthy();
    expect(screen.queryByText('Tea')).toBeNull();

    // Opening the menu loads the whole catalogue so every category can be offered.
    await user.click(screen.getByLabelText(/category/i));
    const option = await screen.findByRole('option', { name: 'Grocery' });
    await user.click(option);

    await waitFor(() => expect(screen.getByText('Tea')).toBeTruthy());
    expect(screen.queryByText('Soap')).toBeNull();
    expect(listProducts).toHaveBeenCalled();
  });

  it('an item with no stock rows counts as out of stock', async () => {
    const user = userEvent.setup();
    wrap();
    await screen.findByText('Soap');
    await user.click(screen.getByLabelText(/stock/i));
    await user.click(await screen.findByRole('option', { name: /out of stock/i }));
    // Neither product has a stock row, so both are out of stock and both are listed.
    await waitFor(() => expect(screen.getByText('Tea')).toBeTruthy());
    expect(within(document.body).getByText('Soap')).toBeTruthy();
  });
});
