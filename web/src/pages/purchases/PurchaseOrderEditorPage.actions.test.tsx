import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { configure, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { PurchaseOrderEditorPage } from '@/pages/purchases/PurchaseOrderEditorPage';

configure({ asyncUtilTimeout: 15_000 });
vi.setConfig({ testTimeout: 40_000 });

const api = vi.hoisted(() => ({
  getPurchaseOrder: vi.fn(),
  convertPurchaseOrder: vi.fn(),
  cancelPurchaseOrder: vi.fn(),
}));

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ user: { id: 1, email: 'o@x.test', fullName: 'Owner', role: 'OWNER', companyId: 9 } }),
}));
vi.mock('@/hooks/useSubscriptionGate', () => ({
  useSubscriptionGate: () => ({ writesBlocked: false, isLoading: false }),
}));
vi.mock('@/api/resources', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/resources')>();
  return {
    ...actual,
    // The server preview is not under test here; the editor falls back to its local totals.
    previewPurchaseTotals: async () => { throw new Error('no preview'); },
    getCompany: async () => ({ id: 9, name: 'Acme', registrationType: 'REGULAR', state: 'Delhi', gstin: '07AAAAA0000A1Z5' }),
    getSupplier: async (id: number) => ({ id, name: `Supplier ${id}`, status: 'ACTIVE', state: 'Delhi' }),
    listSuppliersPage: async () => ({ results: [], count: 0, next: null, previous: null }),
    listProductsPage: async () => ({ results: [], count: 0, next: null, previous: null }),
    searchProducts: async () => [],
    listCustomFieldDefinitions: async () => [],
    fetchSupplierNudge: async () => ({ rows: [] }),
    getPurchaseOrder: (...args: unknown[]) => api.getPurchaseOrder(...args),
    convertPurchaseOrder: (...args: unknown[]) => api.convertPurchaseOrder(...args),
    cancelPurchaseOrder: (...args: unknown[]) => api.cancelPurchaseOrder(...args),
  };
});

const order = (over: Record<string, unknown> = {}) => ({
  id: 5,
  number: 'PO-5',
  status: 'DRAFT',
  supplier: 31,
  purchaseType: 'GST',
  orderDate: '2026-09-01',
  notes: '',
  items: [{ id: 81, product: 201, productName: 'Widget', quantity: '3', unitPrice: '60', gstRate: '18', cessRate: '0' }],
  ...over,
});

function Where() {
  const loc = useLocation();
  const state = loc.state as { message?: string } | null;
  return <div>at {loc.pathname} {state?.message}</div>;
}

function mount() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/purchases/orders/5']}>
        <Routes>
          <Route path="/purchases/orders/:id" element={<PurchaseOrderEditorPage />} />
          <Route path="/purchases/orders" element={<Where />} />
          <Route path="/purchases/history/:id" element={<Where />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => vi.clearAllMocks());

describe('PurchaseOrderEditorPage actions (WP-6)', () => {
  it('asks before creating a bill and opens the bill it created', async () => {
    api.getPurchaseOrder.mockResolvedValue(order());
    api.convertPurchaseOrder.mockResolvedValue({ id: 91, number: 'PUR-91' });
    mount();
    await userEvent.click(await screen.findByRole('button', { name: /^create bill$/i }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText(/draft purchase bill from PO-5/i)).toBeInTheDocument();
    expect(api.convertPurchaseOrder).not.toHaveBeenCalled();
    await userEvent.click(within(dialog).getByRole('button', { name: /^create bill$/i }));
    expect(await screen.findByText(/at \/purchases\/history\/91 .*PUR-91 created from the order/)).toBeInTheDocument();
    expect(api.convertPurchaseOrder).toHaveBeenCalledTimes(1);
  });

  it('does not convert when the dialog is dismissed', async () => {
    api.getPurchaseOrder.mockResolvedValue(order());
    mount();
    await userEvent.click(await screen.findByRole('button', { name: /^create bill$/i }));
    await userEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: /^cancel$/i }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(api.convertPurchaseOrder).not.toHaveBeenCalled();
  });

  it('asks before cancelling the order', async () => {
    api.getPurchaseOrder.mockResolvedValue(order());
    api.cancelPurchaseOrder.mockResolvedValue(order({ status: 'CANCELLED' }));
    mount();
    // Two buttons read "Cancel" once the dialog is open; the first one is the order action.
    await userEvent.click(await screen.findByRole('button', { name: /^cancel$/i }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText(/cancel purchase order PO-5/i)).toBeInTheDocument();
    expect(api.cancelPurchaseOrder).not.toHaveBeenCalled();
    const buttons = within(dialog).getAllByRole('button');
    await userEvent.click(buttons[buttons.length - 1]);
    await waitFor(() => expect(api.cancelPurchaseOrder).toHaveBeenCalledTimes(1));
    expect(await screen.findByText(/at \/purchases\/orders/)).toBeInTheDocument();
  });

  it('tells the user a converted order already became a bill and links to it', async () => {
    api.getPurchaseOrder.mockResolvedValue(order({ status: 'CONVERTED', convertedPurchase: 77 }));
    mount();
    expect(await screen.findByText(/converted to a bill/i)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /open bill/i })).toHaveAttribute('href', '/purchases/history/77');
    expect(screen.queryByRole('button', { name: /^create bill$/i })).not.toBeInTheDocument();
  });
});
