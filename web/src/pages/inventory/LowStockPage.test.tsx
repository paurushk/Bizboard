import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import type { ReactElement } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { LowStockPage } from '@/pages/inventory/LowStockPage';

const listLowStock = vi.hoisted(() => vi.fn());

vi.mock('@/api/resources', () => ({
  listLowStock: () => listLowStock(),
}));

function wrap(ui: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('LowStockPage', () => {
  it('says the shop is well stocked when nothing is below reorder', async () => {
    listLowStock.mockResolvedValueOnce([]);
    wrap(<LowStockPage />);
    expect(await screen.findByText('All items are well stocked above reorder levels.')).toBeTruthy();
  });

  it('names the available and reorder columns in plain language', async () => {
    listLowStock.mockResolvedValueOnce([
      { product: 1, productName: 'Tea', sku: 'TEA', available: 1, reorderLevel: 5, warehouse: 1 },
    ]);
    wrap(<LowStockPage />);
    expect(await screen.findByText('Tea')).toBeTruthy();
    expect(screen.getByText('Available')).toBeTruthy();
    expect(screen.getByText('Reorder Level')).toBeTruthy();
    expect(screen.getByText('At or below reorder')).toBeTruthy();
  });
});
