import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { StockValuationPage } from '@/pages/reports/StockValuationPage';
import { buildValuationCsv, normalizeValuationRow } from '@/pages/reports/valuationHelpers';

const getStockValuation = vi.hoisted(() => vi.fn());

vi.mock('@/api/resources', () => ({
  getStockValuation: (...a: unknown[]) => getStockValuation(...a),
  listWarehouses: async () => [{ id: 1, name: 'Main' }],
}));
vi.mock('@/components/VirtualizedTable', () => ({
  VirtualizedTable: ({ children, rowCount }: { children: (a: unknown) => unknown; rowCount: number }) =>
    children({
      rows: Array.from({ length: rowCount }, (_, i) => ({ index: i, start: i * 52, end: (i + 1) * 52, size: 52, key: i })),
      totalSize: rowCount * 52,
      measureElement: () => undefined,
    }),
}));

const item = { product: 1, productName: 'Tea', warehouseName: 'Main', qty: '95', unitCost: '50', value: '4750.00' };

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <StockValuationPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('valuation helpers', () => {
  it('reads the field names the API has used over time', () => {
    const row = normalizeValuationRow({ product_name: 'Tea', warehouse_name: 'Main', qty: '2', unit_cost: '5', stockValue: '10' });
    expect(row).toMatchObject({ productName: 'Tea', warehouseName: 'Main', quantity: '2', unitCost: '5', value: '10' });
  });
  it('writes a CSV a spreadsheet will not run as a formula', () => {
    const csv = buildValuationCsv(
      [{ productName: '=HYPERLINK("x")', warehouseName: 'Main, North', quantity: '1', unitCost: '2', value: '2' }],
      true,
    );
    const [header, line] = csv.split('\r\n');
    expect(header).toBe('Product,Godown,Qty,Unit cost,Value');
    expect(line).toContain(`"'=HYPERLINK(""x"")"`);
    expect(line).toContain('"Main, North"');
    expect(buildValuationCsv([], false).split('\r\n')[0]).toContain('Unit price');
  });
});

describe('StockValuationPage', () => {
  beforeEach(() => {
    getStockValuation.mockReset();
  });

  it('says the stock value matches the books when it does', async () => {
    getStockValuation.mockResolvedValue({
      method: 'WAVG', items: [item], stockValue: '4750.00', inventoryInBooks: '4750.00', booksVariance: '0.00', stockWritesPosted: true,
    });
    renderPage();
    expect(await screen.findByText(/Stock value matches the books/)).toBeTruthy();
  });

  it('shows the gap to the books and what to do about it', async () => {
    getStockValuation.mockResolvedValue({
      method: 'WAVG', items: [item], stockValue: '4750.00', inventoryInBooks: '5000.00', booksVariance: '-250.00', stockWritesPosted: false,
    });
    renderPage();
    expect(await screen.findByText(/a difference of ₹250.00/)).toBeTruthy();
    expect(screen.getByText(/not posted to the books yet/)).toBeTruthy();
  });

  it('asks for a date and a godown from the server and labels a price view as information only', async () => {
    getStockValuation.mockResolvedValue({ method: 'WAVG', items: [item] });
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Tea');
    expect(screen.queryByText(/difference of/)).toBeNull();
    await user.type(screen.getByLabelText('As of'), '2026-09-30');
    await waitFor(() => expect(getStockValuation).toHaveBeenLastCalledWith(expect.objectContaining({ as_of: '2026-09-30' })));
    await user.click(screen.getByRole('combobox', { name: /value stock at/i }));
    await user.click(await screen.findByRole('option', { name: 'MRP' }));
    expect(await screen.findByText(/not your accounting stock value/)).toBeTruthy();
    expect(screen.getAllByText('Unit price').length).toBeGreaterThan(0);
  });
});
