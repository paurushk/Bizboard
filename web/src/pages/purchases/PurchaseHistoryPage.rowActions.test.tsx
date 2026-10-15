import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { PurchaseHistoryPage } from '@/pages/purchases/PurchaseHistoryPage';
import { registerGlobalConfirm } from '@/utils/confirmBridge';

const api = vi.hoisted(() => ({
  listPurchasesPage: vi.fn(),
  completePurchase: vi.fn(),
  cancelPurchase: vi.fn(),
}));

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ user: { id: 1, email: 'o@x.test', fullName: 'Owner', role: 'OWNER', companyId: 9 } }),
}));
vi.mock('@/hooks/usePartySearch', () => ({
  useSupplierSearch: () => ({ options: [], setQuery: vi.fn(), isFetching: false, enabled: true }),
  useCustomerSearch: () => ({ options: [], setQuery: vi.fn(), isFetching: false, enabled: true }),
}));
vi.mock('@/api/resources', async (orig) => ({ ...(await orig<typeof import('@/api/resources')>()), ...api }));
vi.mock('@/components/VirtualizedTable', () => ({
  VirtualizedTable: ({ rowCount, children }: { rowCount?: number; children: (a: unknown) => ReactNode }) => {
    const count = rowCount ?? 0;
    const rows = Array.from({ length: count }, (_, index) => ({ index, start: index * 52, end: (index + 1) * 52, size: 52 }));
    return children({ rows, totalSize: count * 52, measureElement: () => {} });
  },
}));

function mount() {
  api.listPurchasesPage.mockResolvedValue({
    results: [
      { id: 1, number: '', status: 'DRAFT', supplierName: 'Acme', invoiceDate: '2026-09-12', grandTotal: '100.00' },
      { id: 2, number: 'PUR-2', status: 'COMPLETED', supplierName: 'Beta', invoiceDate: '2026-09-13', grandTotal: '200.00' },
    ],
    count: 2, next: null, previous: null,
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <PurchaseHistoryPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('purchase bill list row actions', () => {
  afterEach(() => registerGlobalConfirm(null));

  it('shows the draft title in words and asks before a one-click Complete', async () => {
    const ask = vi.fn().mockResolvedValue(false);
    registerGlobalConfirm(ask);
    const user = userEvent.setup();
    mount();
    expect(await screen.findByText('Draft #1')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Complete' }));
    await waitFor(() => expect(ask).toHaveBeenCalledTimes(1));
    expect(api.completePurchase).not.toHaveBeenCalled();
  });

  it('puts Cancel on a completed bill in view, behind a confirm', async () => {
    const ask = vi.fn().mockResolvedValueOnce(false).mockResolvedValueOnce(true);
    registerGlobalConfirm(ask);
    api.cancelPurchase.mockResolvedValue({ id: 2, status: 'CANCELLED' });
    const user = userEvent.setup();
    mount();
    await screen.findByText('PUR-2');
    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    await waitFor(() => expect(ask).toHaveBeenCalledTimes(1));
    expect(api.cancelPurchase).not.toHaveBeenCalled();
    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    await waitFor(() => expect(api.cancelPurchase).toHaveBeenCalled());
  });
});
