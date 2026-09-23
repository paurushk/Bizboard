import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import type { ReactElement } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { StockTransferPage } from '@/pages/phase/InventoryPhasePages';
import type { Product } from '@/types/domain';

const product = { id: 8, name: 'Transfer soap', sku: 'TS', trackSerial: false } as Product;

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ user: { id: 1, companyId: 1, role: 'OWNER' } }),
}));

vi.mock('@/pages/inventory/useStockOffline', () => ({
  useStockOffline: () => undefined,
}));

vi.mock('@/hooks/useSubscriptionGate', () => ({
  useSubscriptionGate: () => ({ writesBlocked: false }),
}));

vi.mock('@/hooks/useActiveCustomFieldDefs', () => ({
  useVisibleCustomFieldDefs: () => [],
}));

vi.mock('@/hooks/useProductSearch', () => ({
  useProductSearch: () => ({
    productQuery: '',
    setProductQuery: () => undefined,
    options: [product],
    isFetching: false,
    truncated: false,
    helperText: undefined,
    enabled: true,
    count: 1,
  }),
}));

vi.mock('@/api/resources', () => ({
  listTransfers: async () => [],
  listWarehouses: async () => [
    { id: 1, name: 'Main' },
    { id: 2, name: 'Shop' },
  ],
  getProduct: async () => product,
  createTransfer: vi.fn(),
  completeTransfer: vi.fn(),
  cancelTransfer: vi.fn(),
  listBatches: async () => [],
}));

function wrap(ui: ReactElement, path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('Stock transfer replenishment prefill', () => {
  it('opens the transfer dialog with the suggested quantity', async () => {
    wrap(<StockTransferPage />, '/inventory/transfers?product=8&qty=6&from=2&to=1');
    expect(await screen.findByRole('heading', { name: 'New stock transfer' })).toBeTruthy();
    expect(screen.getByDisplayValue('6')).toBeTruthy();
  });
});
