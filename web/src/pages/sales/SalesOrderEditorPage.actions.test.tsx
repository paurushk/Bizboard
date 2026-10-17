import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { configure, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { SalesOrderEditorPage } from '@/pages/sales/SalesOrderEditorPage';

configure({ asyncUtilTimeout: 15_000 });
vi.setConfig({ testTimeout: 40_000 });

const state = vi.hoisted(() => ({ gates: false }));
const api = vi.hoisted(() => ({
  getSalesOrder: vi.fn(),
  cancelSalesOrder: vi.fn(),
  confirmSalesOrder: vi.fn(),
  checkSalesOrderGate: vi.fn(),
  updateSalesOrder: vi.fn(),
}));

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 1, email: 'owner@x.test', fullName: 'Owner', role: 'OWNER', companyId: 9 },
  }),
}));
vi.mock('@/hooks/useSubscriptionGate', () => ({
  useSubscriptionGate: () => ({ writesBlocked: false, isLoading: false }),
}));
vi.mock('@/api/payroll', () => ({
  listEmployeesPage: async () => ({ results: [], count: 0, next: null, previous: null }),
}));
vi.mock('@/config/featureFlags', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/config/featureFlags')>();
  return {
    ...actual,
    isRuntimeFlagEnabled: (name: string) => (name === 'ENABLE_ORDER_GATES' ? state.gates : false),
    useFeatureFlagEpoch: () => 0,
  };
});
vi.mock('@/api/osPlan', () => ({
  checkSalesOrderGate: (...a: unknown[]) => api.checkSalesOrderGate(...a),
  confirmSalesOrder: (...a: unknown[]) => api.confirmSalesOrder(...a),
}));
vi.mock('@/api/resources', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/resources')>();
  return {
    ...actual,
    getCompany: async () => ({ id: 9, name: 'Acme', registrationType: 'REGULAR', state: 'Delhi', gstin: '07AAAAA0000A1Z5' }),
    getCustomer: async (id: number) => ({ id, name: 'Anil Store', status: 'ACTIVE', state: 'Delhi' }),
    listCustomersPage: async () => ({ results: [], count: 0, next: null, previous: null }),
    listProductsPage: async () => ({ results: [], count: 0, next: null, previous: null }),
    searchProducts: async () => [],
    listCustomFieldDefinitions: async () => [],
    getProduct: async () => ({ id: 201, name: 'Widget', sku: 'WID-1', sellingPrice: 100, unitName: 'PCS', status: 'ACTIVE', gstRate: 18 }),
    getSalesOrder: (...args: unknown[]) => api.getSalesOrder(...args),
    cancelSalesOrder: (...args: unknown[]) => api.cancelSalesOrder(...args),
    updateSalesOrder: (...args: unknown[]) => api.updateSalesOrder(...args),
  };
});

const order = (status: string, extra: Record<string, unknown> = {}) => ({
  id: 5,
  status,
  customer: 10,
  invoiceType: 'GST',
  orderDate: '2026-09-01',
  expectedDelivery: '2026-09-10',
  paymentTermsDays: 15,
  notes: '',
  items: [
    { id: 71, product: 201, productName: 'Widget', quantity: '2', unitPrice: '100', gstRate: '18', cessRate: '0', discountPercent: '0' },
  ],
  ...extra,
});

function mount() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/sales/orders/5']}>
        <Routes>
          <Route path="/sales/orders/:id" element={<SalesOrderEditorPage />} />
          <Route path="/sales/orders" element={<div>orders list</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

async function openAs(status: string, extra: Record<string, unknown> = {}) {
  api.getSalesOrder.mockResolvedValue(order(status, extra));
  mount();
  await screen.findByText('Widget');
}

const button = (name: string) => screen.queryByRole('button', { name });

beforeEach(() => {
  state.gates = false;
  Object.values(api).forEach((fn) => fn.mockReset());
  api.cancelSalesOrder.mockResolvedValue({});
  api.confirmSalesOrder.mockResolvedValue({});
  api.updateSalesOrder.mockImplementation(async (_id: number, payload: Record<string, unknown>) => ({ ...order('DRAFT'), ...payload }));
});

describe('SalesOrderEditorPage — actions follow the order status (H-05, H-06)', () => {
  it('a confirmed order can be converted and cancelled with order checks off (the Quick Entry path)', async () => {
    await openAs('CONFIRMED');
    expect(button('Convert to invoice')).not.toBeNull();
    expect(button('Convert to challan')).not.toBeNull();
    expect(button('Cancel')).not.toBeNull();
    expect(button('Confirm')).toBeNull();
    expect(screen.getByText('Confirmed')).toBeInTheDocument();
  });

  it('a confirmed order offers the same with order checks on', async () => {
    state.gates = true;
    await openAs('CONFIRMED');
    expect(button('Convert to invoice')).not.toBeNull();
    expect(button('Convert to challan')).not.toBeNull();
  });

  it('a draft with order checks off can be confirmed straight away', async () => {
    await openAs('DRAFT');
    expect(button('Confirm')).not.toBeNull();
    expect(button('Convert to invoice')).not.toBeNull();
    fireEvent.click(button('Confirm') as HTMLElement);
    await waitFor(() => expect(api.confirmSalesOrder).toHaveBeenCalledTimes(1));
    expect(api.checkSalesOrderGate).not.toHaveBeenCalled();
  });

  it('a draft with order checks on must be confirmed first and goes through the credit and margin check', async () => {
    state.gates = true;
    api.checkSalesOrderGate.mockResolvedValue({ creditBlocked: false, creditMessage: '', marginWarnings: [] });
    await openAs('DRAFT');
    expect(button('Convert to invoice')).toBeNull();
    expect(button('Convert to challan')).toBeNull();
    fireEvent.click(button('Confirm') as HTMLElement);
    await waitFor(() => expect(api.checkSalesOrderGate).toHaveBeenCalledTimes(1));
  });

  it('a partly processed order offers the remainder and no cancel', async () => {
    await openAs('PARTIALLY_CONVERTED');
    expect(button('Convert to invoice')).not.toBeNull();
    expect(button('Cancel')).toBeNull();
    expect(screen.getByText('Partly processed')).toBeInTheDocument();
  });

  it('a shipped, unbilled order reads Shipped and offers nothing', async () => {
    await openAs('CONVERTED', { fulfilmentState: 'shipped_not_invoiced' });
    expect(screen.getByText('Shipped')).toBeInTheDocument();
    expect(button('Convert to invoice')).toBeNull();
    expect(button('Cancel')).toBeNull();
  });

  it('cancelling a confirmed order asks first and says the stock will be released', async () => {
    await openAs('CONFIRMED');
    fireEvent.click(button('Cancel') as HTMLElement);
    expect(await screen.findByText(/stock reserved for it will be released/i)).toBeInTheDocument();
    expect(api.cancelSalesOrder).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Confirm cancel' }));
    await waitFor(() => expect(api.cancelSalesOrder).toHaveBeenCalledTimes(1));
  });
});
