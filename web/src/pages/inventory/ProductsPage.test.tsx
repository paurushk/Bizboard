import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ProductsPage } from '@/pages/inventory/ProductsPage';

const listProductsPage = vi.hoisted(() => vi.fn());
const listProducts = vi.hoisted(() => vi.fn());
const listStock = vi.hoisted(() => vi.fn());
const listLowStock = vi.hoisted(() => vi.fn());

const markProductsReviewed = vi.hoisted(() => vi.fn());
const getProductFilterOptions = vi.hoisted(() => vi.fn());

vi.mock('@/api/resources', () => ({
  deleteProduct: vi.fn(),
  getProductFilterOptions: () => getProductFilterOptions(),
  markProductsReviewed: (...args: unknown[]) => markProductsReviewed(...args),
  listProducts: (...args: unknown[]) => listProducts(...args),
  listProductsPage: (...args: unknown[]) => listProductsPage(...args),
  listStock: (...args: unknown[]) => listStock(...args),
  listLowStock: (...args: unknown[]) => listLowStock(...args),
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

function wrap(entry = '/') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[entry]}>
        <ProductsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('ProductsPage filters', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getProductFilterOptions.mockResolvedValue({
      categories: [{ id: 3, name: 'Grocery' }, { id: 4, name: 'Home' }],
      brands: [{ id: 8, name: 'Acme' }],
      gstRates: ['5.00', '18.00'],
    });
    listProductsPage.mockResolvedValue({ count: 2, next: 'page2', previous: null, results: [product(1, 'Soap', 'Home')] });
    listProducts.mockResolvedValue([product(1, 'Soap', 'Home'), product(2, 'Tea', 'Grocery')]);
    listStock.mockResolvedValue([]);
    listLowStock.mockResolvedValue([]);
  });

  it('offers the categories in use without loading the whole catalogue, and asks the server to filter', async () => {
    const user = userEvent.setup();
    wrap();
    expect(await screen.findByText('Soap')).toBeTruthy();
    listProductsPage.mockResolvedValue({ count: 1, next: null, previous: null, results: [product(2, 'Tea', 'Grocery')] });

    await user.click(screen.getByLabelText(/category/i));
    await user.click(await screen.findByRole('option', { name: 'Grocery' }));

    await waitFor(() => expect(screen.getByText('Tea')).toBeTruthy());
    expect(screen.queryByText('Soap')).toBeNull();
    expect(listProductsPage).toHaveBeenLastCalledWith(expect.objectContaining({ category: '3', page: 1 }));
    // Nothing downloaded the whole catalogue just to fill a menu or filter it.
    expect(listProducts).not.toHaveBeenCalled();
  });

  it('sends the stock status and the tax slab to the server', async () => {
    const user = userEvent.setup();
    wrap();
    await screen.findByText('Soap');
    await user.click(screen.getByLabelText(/stock/i));
    await user.click(await screen.findByRole('option', { name: /out of stock/i }));
    await waitFor(() => expect(listProductsPage).toHaveBeenLastCalledWith(expect.objectContaining({ stockStatus: 'out' })));
    await user.click(screen.getByLabelText(/tax slab/i));
    await user.click(await screen.findByRole('option', { name: '18%' }));
    await waitFor(() =>
      expect(listProductsPage).toHaveBeenLastCalledWith(expect.objectContaining({ stockStatus: 'out', gstRate: '18' })),
    );
  });

  it('calls the "in stock" filter what it is: low items included', async () => {
    const user = userEvent.setup();
    wrap();
    await screen.findByText('Soap');
    await user.click(screen.getByLabelText(/stock/i));
    expect(await screen.findByRole('option', { name: 'In stock (incl. low)' })).toBeTruthy();
  });

  it('exports the same search and filters the list shows, every page', async () => {
    const user = userEvent.setup();
    URL.createObjectURL = vi.fn(() => 'blob:x');
    URL.revokeObjectURL = vi.fn();
    wrap();
    await screen.findByText('Soap');
    await user.click(screen.getByLabelText(/category/i));
    await user.click(await screen.findByRole('option', { name: 'Grocery' }));
    await waitFor(() => expect(listProductsPage).toHaveBeenLastCalledWith(expect.objectContaining({ category: '3' })));
    await user.click(await screen.findByRole('button', { name: /export/i }));
    await waitFor(() => expect(listProducts).toHaveBeenCalledWith(expect.objectContaining({ category: '3' })));
  });
});

describe('ProductsPage low-stock rows', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getProductFilterOptions.mockResolvedValue({ categories: [], brands: [], gstRates: [] });
    listProductsPage.mockResolvedValue({
      count: 2, next: null, previous: null, results: [product(1, 'Soap', 'Home'), product(2, 'Tea', 'Grocery')],
    });
    listProducts.mockResolvedValue([]);
    listStock.mockResolvedValue([
      { product: 1, available: '12', onHand: '12', reserved: '0' },
      { product: 2, available: '12', onHand: '12', reserved: '0' },
    ]);
    listLowStock.mockResolvedValue([{ product: 1, productName: 'Soap', sku: 'SKU-1', hasReorderRule: true }]);
  });

  it('marks as low only the items the alerts call low', async () => {
    wrap();
    await screen.findByText('Soap');
    await waitFor(() => expect(screen.getAllByText('12 PCS')).toHaveLength(2));
    const chipOf = (name: string) =>
      (screen.getByText(name).closest('tr') as HTMLElement).querySelector('.MuiChip-colorWarning, .MuiChip-colorSuccess') as HTMLElement;
    expect(chipOf('Soap').className).toContain('MuiChip-colorWarning');
    expect(chipOf('Tea').className).toContain('MuiChip-colorSuccess');
  });
});

describe('ProductsPage needs-review filter', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getProductFilterOptions.mockResolvedValue({ categories: [], brands: [], gstRates: [] });
    listProductsPage.mockResolvedValue({ count: 1, next: null, previous: null, results: [product(7, 'From a bill', 'Home')] });
    listProducts.mockResolvedValue([]);
    listStock.mockResolvedValue([]);
    listLowStock.mockResolvedValue([]);
    markProductsReviewed.mockResolvedValue({ updated: 1 });
  });

  it('asks the server only for items a bill import created, when opened from the draft notice', async () => {
    wrap('/inventory/products?needsReview=1');
    await screen.findByText('From a bill');
    expect(listProductsPage).toHaveBeenCalledWith(expect.objectContaining({ needsReview: true }));
    expect(screen.getByText(/have no cost or stock yet/i)).toBeInTheDocument();
  });

  it('marks the listed items as reviewed', async () => {
    wrap('/inventory/products?needsReview=1');
    await screen.findByText('From a bill');
    await userEvent.click(screen.getByRole('button', { name: 'Mark these as reviewed' }));
    await waitFor(() => expect(markProductsReviewed).toHaveBeenCalledWith([7]));
  });

  it('does not filter by default', async () => {
    wrap('/');
    await screen.findByText('From a bill');
    expect(listProductsPage).toHaveBeenCalledWith(expect.objectContaining({ needsReview: false }));
  });
});
