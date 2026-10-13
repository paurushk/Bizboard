import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
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

const PURCHASE = {
  id: 5,
  number: 'PUR-0005',
  supplier: 8,
  supplierName: 'Mega Suppliers',
  status: 'COMPLETED',
  items: [
    {
      id: 51,
      product: 6,
      productName: 'Phone',
      quantity: '3',
      unitPrice: '400',
      gstRate: '0',
      serialNumbers: ['P-1', 'P-2', 'P-3'],
    },
  ],
};

const createPurchaseReturn = vi.fn(async () => ({ id: 70 }));
const completePurchaseReturn = vi.fn(async () => ({ id: 70, status: 'COMPLETED' }));

vi.mock('@/api/resources', () => ({
  listPurchaseReturnsPage: async () => ({ results: [], count: 0, next: null, previous: null }),
  listPurchaseReturns: async () => [],
  listPurchasesPage: async () => ({ results: [PURCHASE], count: 1, next: null, previous: null }),
  listProducts: async () => [{ id: 6, name: 'Phone', sku: 'PH', trackSerial: true }],
  getPurchase: vi.fn(async () => PURCHASE),
  createPurchaseReturn: (...args: unknown[]) => createPurchaseReturn(...(args as [])),
  completePurchaseReturn: (...args: unknown[]) => completePurchaseReturn(...(args as [])),
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

describe('PurchaseReturnsPage serial returns', () => {
  it('picks the first received serial on tick and sends quantity equal to the picks', async () => {
    mount('/purchases/returns?create=1');
    await screen.findByRole('dialog', { name: t('phase1.newPurchaseReturn') });
    const user = userEvent.setup();
    await user.click(screen.getByRole('combobox', { name: /original purchase/i }));
    await user.click(await screen.findByRole('option', { name: /PUR-0005/ }));
    fireEvent.click(await screen.findByRole('checkbox'));
    const p2 = await screen.findByText('P-2');
    fireEvent.click(p2);
    fireEvent.click(screen.getByRole('button', { name: /^complete$/i }));
    await waitFor(() => expect(createPurchaseReturn).toHaveBeenCalledTimes(1));
    const payload = createPurchaseReturn.mock.calls[0] as unknown as [{ items: Array<Record<string, unknown>> }];
    expect(payload[0].items[0]).toEqual(
      expect.objectContaining({ product: 6, quantity: 2, serialNumbers: ['P-1', 'P-2'] }),
    );
  });
});
