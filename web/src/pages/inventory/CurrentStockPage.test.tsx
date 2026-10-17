import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { CurrentStockPage } from '@/pages/inventory/CurrentStockPage';
import { lotKey } from '@/pages/inventory/stockListHelpers';

const listStockByProduct = vi.hoisted(() => vi.fn());
const listAllStockByProduct = vi.hoisted(() => vi.fn());
const listStock = vi.hoisted(() => vi.fn());
const getInventorySummary = vi.hoisted(() => vi.fn());
const exportReport = vi.hoisted(() => vi.fn());

vi.mock('@/api/resources', () => ({
  listStockByProduct: (...a: unknown[]) => listStockByProduct(...a),
  listAllStockByProduct: (...a: unknown[]) => listAllStockByProduct(...a),
  listStock: (...a: unknown[]) => listStock(...a),
  getInventorySummary: () => getInventorySummary(),
  listWarehouses: async () => [{ id: 1, name: 'Main' }, { id: 2, name: 'North' }],
  exportReport: (...a: unknown[]) => exportReport(...a),
}));
vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ user: { id: 1, companyId: 1, role: 'OWNER', canExport: true } }),
}));
vi.mock('@/hooks/useActiveCustomFieldDefs', () => ({ useVisibleCustomFieldDefs: () => [] }));
vi.mock('@/components/VirtualizedTable', () => ({
  VirtualizedTable: ({ children, rowCount }: { children: (a: unknown) => unknown; rowCount: number }) =>
    children({
      rows: Array.from({ length: rowCount }, (_, i) => ({ index: i, start: i * 52, end: (i + 1) * 52, size: 52, key: i })),
      totalSize: rowCount * 52,
      measureElement: () => undefined,
    }),
}));

const group = (over: Record<string, unknown>) => ({
  product: 1, productName: 'Tea', sku: 'T1', rackCode: '', warehouse: null, onHand: '8', reserved: '0',
  available: '8', lots: 1, nearestExpiry: null, ...over,
});
const page = (results: unknown[], over: Record<string, unknown> = {}) => ({
  results, count: results.length, next: null,
  summary: { items: results.length, itemsInStock: 1, itemsOut: 1 }, ...over,
});

function renderPage(path = '/inventory/stock') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <CurrentStockPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('CurrentStockPage', () => {
  beforeEach(() => {
    for (const fn of [listStockByProduct, listAllStockByProduct, listStock, getInventorySummary, exportReport]) fn.mockReset();
    listStockByProduct.mockResolvedValue(
      page([group({}), group({ product: 2, productName: 'Rice', sku: 'R1', onHand: '0', available: '0' })]),
    );
    listAllStockByProduct.mockResolvedValue([]);
    listStock.mockResolvedValue([]);
    getInventorySummary.mockResolvedValue({
      rows: [
        { product: 'Tea', sku: 'T1', warehouseId: 1, stockValue: '100' },
        { product: 'Rice', sku: 'R1', warehouseId: 1, stockValue: '0' },
      ],
    });
  });

  it('shows items in and out of stock from the server, and the value of what is shown', async () => {
    renderPage();
    expect(await screen.findByText('Items in stock: 1')).toBeTruthy();
    expect(screen.getByText('Out of stock: 1')).toBeTruthy();
    await waitFor(() => expect(screen.getByText(/Total stock value/)).toBeTruthy());
  });

  it('shows no stock value, and no zero, when the books are not theirs to read', async () => {
    getInventorySummary.mockRejectedValue(new Error('Forbidden'));
    renderPage();
    expect(await screen.findByText('Items in stock: 1')).toBeTruthy();
    await waitFor(() => expect(getInventorySummary).toHaveBeenCalled());
    expect(screen.queryByText(/Total stock value/)).toBeNull();
  });

  it('has no email button (it mailed a link that only worked in this browser tab)', async () => {
    renderPage();
    await screen.findByText('Items in stock: 1');
    expect(screen.queryByRole('button', { name: /email/i })).toBeNull();
    expect(screen.getByRole('button', { name: 'Download CSV' })).toBeTruthy();
  });

  it('asks the server for the chosen godown', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Items in stock: 1');
    await user.click(screen.getByRole('combobox', { name: /godown|warehouse/i }));
    await user.click(await screen.findByRole('option', { name: 'North' }));
    await waitFor(() => expect(listStockByProduct).toHaveBeenLastCalledWith(expect.objectContaining({ warehouse: 2, page: 1 })));
  });

  it('reads its filters from the address bar', async () => {
    renderPage('/inventory/stock?warehouse=2&sort=available&out=1&q=tea');
    await waitFor(() =>
      expect(listStockByProduct).toHaveBeenCalledWith(
        expect.objectContaining({ warehouse: 2, ordering: 'available', negative: true, q: 'tea' }),
      ),
    );
  });

  it('sorts and filters to what is out of stock on the server', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Items in stock: 1');
    await user.click(screen.getByRole('checkbox', { name: 'Only out of stock or negative' }));
    await waitFor(() => expect(listStockByProduct).toHaveBeenLastCalledWith(expect.objectContaining({ negative: true })));
    await user.click(screen.getByRole('combobox', { name: 'Sort by' }));
    await user.click(await screen.findByRole('option', { name: 'Most available first' }));
    await waitFor(() => expect(listStockByProduct).toHaveBeenLastCalledWith(expect.objectContaining({ ordering: '-available' })));
  });

  it('shows how many items there are and loads the next page on request', async () => {
    listStockByProduct.mockReset();
    listStockByProduct
      .mockResolvedValueOnce(page([group({})], { count: 2, next: '?page=2' }))
      .mockResolvedValueOnce(page([group({ product: 2, productName: 'Rice', sku: 'R1' })], { count: 2 }));
    const user = userEvent.setup();
    renderPage();
    expect(await screen.findByText('Showing 1 of 2 items')).toBeTruthy();
    await user.click(screen.getByRole('button', { name: 'Show more items' }));
    expect(await screen.findByText('Showing 2 of 2 items')).toBeTruthy();
    expect(listStockByProduct).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2 }));
    expect(screen.queryByRole('button', { name: 'Show more items' })).toBeNull();
  });

  it('loads the lots of an item only when it is opened, and keys two lots apart', async () => {
    listStock.mockResolvedValue([
      { id: 11, product: 1, warehouse: 1, batch: 5, batchNo: 'L1', onHand: '3', reserved: '0', available: '3' },
      { id: 12, product: 1, warehouse: 1, batch: 6, batchNo: 'L2', onHand: '5', reserved: '0', available: '5' },
    ]);
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Items in stock: 1');
    expect(listStock).not.toHaveBeenCalled();
    await user.click(screen.getAllByRole('button', { name: 'Show lots' })[0]);
    expect(await screen.findByText('L1')).toBeTruthy();
    expect(screen.getByText('L2')).toBeTruthy();
    expect(listStock).toHaveBeenCalledWith({ productIds: [1], warehouse: undefined });
    expect(lotKey({ product: 1, warehouse: 1, batch: 5, id: 11 })).not.toBe(lotKey({ product: 1, warehouse: 1, batch: 6, id: 12 }));
    expect(lotKey({ product: 1, warehouse: 1, batch: null })).not.toBe(lotKey({ product: 1, warehouse: 1, batch: 6 }));
  });

  it('prints every row, not just the ones on screen', async () => {
    listAllStockByProduct.mockResolvedValue(
      Array.from({ length: 300 }, (_, i) => group({ product: 100 + i, productName: `Item ${i}`, sku: `S${i}` })),
    );
    let printed = 0;
    vi.spyOn(window, 'print').mockImplementation(() => {
      printed = within(screen.getByRole('table', { name: 'Current stock for printing', hidden: true })).getAllByRole('row', { hidden: true }).length;
    });
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Items in stock: 1');
    await user.click(screen.getByRole('button', { name: 'Print' }));
    await waitFor(() => expect(window.print).toHaveBeenCalledTimes(1));
    expect(printed).toBe(301); // header + 300 rows
    expect(listAllStockByProduct).toHaveBeenCalledWith(expect.objectContaining({ ordering: 'name' }));
  });

  it('exports the same godown and search the page shows', async () => {
    exportReport.mockResolvedValue({ url: 'blob:x' });
    const user = userEvent.setup();
    renderPage('/inventory/stock?warehouse=2&q=tea');
    await screen.findByText('Items in stock: 1');
    await user.click(screen.getByRole('button', { name: 'Download CSV' }));
    await waitFor(() => expect(exportReport).toHaveBeenCalledWith('inventory', { warehouse: '2', q: 'tea' }));
  });

  it('warns when a balance disagrees with the movement history', async () => {
    getInventorySummary.mockResolvedValue({
      rows: [{ product: 'Tea', sku: 'T1', warehouseId: 1, stockValue: '100', balanceDrift: true }],
    });
    renderPage();
    expect(await screen.findByText(/do not match the stock movement history/)).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Open report' }).getAttribute('href')).toBe('/reports/inventory');
  });
});
