import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { PurchaseReturnsPage } from '@/pages/purchases/PurchaseReturnsPage';
import { t } from '@/i18n';

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 1, email: 'owner@x.test', fullName: 'Owner', role: 'OWNER', companyId: 9 },
  }),
}));

vi.mock('@/hooks/useSubscriptionGate', () => ({
  useSubscriptionGate: () => ({ writesBlocked: false, isLoading: false }),
}));

vi.mock('@/api/resources', () => ({
  listPurchaseReturnsPage: async () => ({ results: [], count: 0, next: null, previous: null }),
  listPurchaseReturns: async () => [],
  listPurchasesPage: async () => ({ results: [], count: 0, next: null, previous: null }),
  listProducts: async () => [],
  getPurchase: vi.fn(),
  createPurchaseReturn: vi.fn(),
  completePurchaseReturn: vi.fn(),
  updatePurchaseReturn: vi.fn(),
}));

function SearchProbe() {
  const location = useLocation();
  return <div data-testid="search">{location.search}</div>;
}

function mount(path: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <SearchProbe />
        <Routes>
          <Route path="/purchases/returns" element={<PurchaseReturnsPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('PurchaseReturnsPage inbound ?create=1', () => {
  it('opens the new-return dialog and removes the parameter from the address', async () => {
    mount('/purchases/returns?create=1');
    expect(await screen.findByRole('dialog', { name: t('phase1.newPurchaseReturn') })).toBeTruthy();
    await waitFor(() => expect(screen.getByTestId('search').textContent).toBe(''));
  });

  it('does not open the dialog again after it is closed', async () => {
    mount('/purchases/returns?create=1');
    await screen.findByRole('dialog', { name: t('phase1.newPurchaseReturn') });
    await waitFor(() => expect(screen.getByTestId('search').textContent).toBe(''));

    await userEvent.click(screen.getByRole('button', { name: new RegExp(`^${t('common.cancel')}$`, 'i') }));
    await waitFor(() => expect(screen.queryByRole('dialog', { name: t('phase1.newPurchaseReturn') })).toBeNull());
    // Settled: it does not pop open again on a later render.
    await new Promise((resolve) => setTimeout(resolve, 100));
    expect(screen.queryByRole('dialog', { name: t('phase1.newPurchaseReturn') })).toBeNull();
  });

  it('stays closed when the address has no create parameter', async () => {
    mount('/purchases/returns');
    await screen.findByText(t('nav.purchaseReturns'));
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('keeps other parameters in the address when it strips create', async () => {
    mount('/purchases/returns?create=1&q=abc');
    await screen.findByRole('dialog', { name: t('phase1.newPurchaseReturn') });
    await waitFor(() => expect(screen.getByTestId('search').textContent).toBe('?q=abc'));
  });
});
