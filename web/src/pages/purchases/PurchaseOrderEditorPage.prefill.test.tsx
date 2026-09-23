import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import type { ReactElement } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { PurchaseOrderEditorPage } from '@/pages/purchases/PurchaseOrderEditorPage';
import type { Product } from '@/types/domain';

const product = {
  id: 7,
  name: 'Suggested soap',
  sku: 'SOAP',
  purchasePrice: '12',
  sellingPrice: '20',
  gstRate: '0',
  cessRate: '0',
} as Product;

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 1, role: 'OWNER', companyId: 1 },
    isAuthenticated: true,
  }),
}));

vi.mock('@/hooks/useSubscriptionGate', () => ({
  useSubscriptionGate: () => ({ writesBlocked: false, subscription: null, isLoading: false }),
}));

vi.mock('@/hooks/useProductCfFilters', () => ({
  useProductCfFilters: () => ({ cfFilters: undefined, filterBar: null, enabled: false, defs: [] }),
}));

vi.mock('@/hooks/usePartySearch', () => ({
  useSupplierSearch: () => ({
    query: '',
    setQuery: () => undefined,
    options: [],
    isFetching: false,
    enabled: true,
  }),
}));

vi.mock('@/hooks/useProductSearch', () => ({
  useProductSearch: () => ({
    productQuery: '',
    setProductQuery: () => undefined,
    options: [],
    isFetching: false,
    truncated: false,
    helperText: undefined,
    enabled: true,
    count: 0,
  }),
}));

vi.mock('@/api/resources', () => ({
  getCompany: async () => ({ id: 1, name: 'Shop', state: 'Karnataka', gstin: '', registrationType: 'REGULAR', isGstRegistered: false }),
  getProduct: async () => product,
  getSupplier: vi.fn(),
  getPurchaseOrder: vi.fn(),
  createPurchaseOrder: vi.fn(),
  updatePurchaseOrder: vi.fn(),
  cancelPurchaseOrder: vi.fn(),
  convertPurchaseOrder: vi.fn(),
}));

function wrap(ui: ReactElement, path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('Purchase order replenishment prefill', () => {
  it('adds the suggested product and quantity from the query string', async () => {
    wrap(<PurchaseOrderEditorPage />, '/purchases/orders/new?product=7&qty=4&warehouse=2');
    expect(await screen.findByText('Suggested soap')).toBeTruthy();
    expect(screen.getByDisplayValue('4')).toBeTruthy();
  });
});
