import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { describeReference } from '@/pages/inventory/ledgerHelpers';
import { StockLedgerPage } from '@/pages/inventory/StockLedgerPage';

const listStockLedger = vi.hoisted(() => vi.fn());
const exportStockLedger = vi.hoisted(() => vi.fn());
const getProduct = vi.hoisted(() => vi.fn());

vi.mock('@/api/resources', () => ({
  listStockLedger: (...a: unknown[]) => listStockLedger(...a),
  exportStockLedger: (...a: unknown[]) => exportStockLedger(...a),
  getProduct: (...a: unknown[]) => getProduct(...a),
  listWarehouses: async () => [{ id: 1, name: 'Main' }],
}));
vi.mock('@/auth/AuthContext', () => ({ useAuth: () => ({ user: { id: 1, companyId: 1, role: 'OWNER', canExport: true } }) }));
vi.mock('@/hooks/useProductSearch', () => ({
  useProductSearch: () => ({ productQuery: '', setProductQuery: () => undefined, options: [], isFetching: false, helperText: undefined }),
}));

const row = (over: Record<string, unknown>) => ({
  id: 1, movementDate: '2026-10-10', product: 1, productName: 'Tea', sku: 'T1', warehouse: 1, warehouseName: 'Main',
  batch: null, batchNo: null, movementType: 'ADJUSTMENT', movementTypeLabel: 'Adjustment', quantity: '-5',
  runningBalance: null, unitCost: null, reason: 'Damaged', referenceType: 'manual_adjustment', referenceId: '9',
  createdByName: 'Asha', ...over,
});

function renderPage(path = '/inventory/ledger') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <StockLedgerPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('describeReference', () => {
  it('links documents that have a page and names the rest', () => {
    expect(describeReference('sales_invoice', 42)).toEqual({ label: 'Sales invoice #42', href: '/sales/history/42' });
    expect(describeReference('purchase_invoice', '7')).toEqual({ label: 'Purchase bill #7', href: '/purchases/history/7' });
    expect(describeReference('stock_transfer', 3).href).toBe('/inventory/transfers');
    expect(describeReference('manual_adjustment', 9)).toEqual({ label: 'Adjustment #9', href: null });
    expect(describeReference('some_new_thing', 1).label).toBe('Some new thing #1');
    expect(describeReference('', 1)).toEqual({ label: '', href: null });
  });
});

describe('StockLedgerPage', () => {
  beforeEach(() => {
    listStockLedger.mockReset();
    exportStockLedger.mockReset();
    getProduct.mockReset();
    listStockLedger.mockResolvedValue({
      results: [
        row({ id: 2, quantity: '3', movementType: 'PURCHASE', movementTypeLabel: 'Purchase', referenceType: 'purchase_invoice', referenceId: '7', reason: '' }),
        row({ id: 1 }),
      ],
      count: 2, next: null, previous: null,
    });
  });

  it('lists movements with a signed quantity, the reason and a link to the document', async () => {
    renderPage();
    expect(await screen.findByText('Damaged')).toBeTruthy();
    expect(screen.getByText('+3')).toBeTruthy();
    expect(screen.getByText('-5')).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Open Purchase bill #7' }).getAttribute('href')).toBe('/purchases/history/7');
    expect(screen.getByText('Choose an item to see its running balance.')).toBeTruthy();
    expect(screen.queryByRole('columnheader', { name: 'Balance' })).toBeNull();
    expect(screen.queryByRole('columnheader', { name: 'Unit cost' })).toBeNull();
  });

  it('opens on the item and godown a link carries, and shows its running balance', async () => {
    getProduct.mockResolvedValue({ id: 1, name: 'Tea', sku: 'T1' });
    listStockLedger.mockResolvedValue({
      results: [row({ runningBalance: '95', unitCost: '50' })], count: 1, next: null, previous: null,
    });
    renderPage('/inventory/ledger?product=1&warehouse=1');
    expect(await screen.findByRole('columnheader', { name: 'Balance' })).toBeTruthy();
    expect(screen.getByRole('columnheader', { name: 'Unit cost' })).toBeTruthy();
    expect(screen.getByText('95')).toBeTruthy();
    await waitFor(() =>
      expect(listStockLedger).toHaveBeenLastCalledWith(expect.objectContaining({ product: 1, warehouse: 1 }), 1),
    );
  });

  it('says when nothing matches', async () => {
    listStockLedger.mockResolvedValue({ results: [], count: 0, next: null, previous: null });
    renderPage();
    expect(await screen.findByText('No stock movements match.')).toBeTruthy();
  });

  it('downloads the same filtered rows as CSV', async () => {
    exportStockLedger.mockResolvedValue({ url: 'blob:x' });
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Damaged');
    await user.click(screen.getByRole('button', { name: 'Download CSV' }));
    await waitFor(() => expect(exportStockLedger).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(click).toHaveBeenCalled());
    click.mockRestore();
  });

  it('pages through long histories', async () => {
    listStockLedger.mockResolvedValue({ results: [row({})], count: 120, next: 'n', previous: null });
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Damaged');
    await user.click(screen.getByRole('button', { name: 'Next' }));
    await waitFor(() => expect(listStockLedger).toHaveBeenLastCalledWith(expect.anything(), 2));
  });
});
