import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { configure, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { Link, MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { SalesOrderEditorPage } from '@/pages/sales/SalesOrderEditorPage';
import { t } from '@/i18n';

configure({ asyncUtilTimeout: 15_000 });
vi.setConfig({ testTimeout: 40_000 });

const api = vi.hoisted(() => ({
  getSalesOrder: vi.fn(),
  getProduct: vi.fn(),
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

vi.mock('@/api/osPlan', () => ({
  checkSalesOrderGate: vi.fn(),
  confirmSalesOrder: vi.fn(),
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
    getSalesOrder: (...args: unknown[]) => api.getSalesOrder(...args),
    getProduct: (...args: unknown[]) => api.getProduct(...args),
  };
});

const WIDGET = { id: 201, name: 'Widget', sku: 'WID-1', sellingPrice: 100, unitName: 'PCS', status: 'ACTIVE', gstRate: 18 };

const order = (notes: string) => ({
  id: 5,
  status: 'DRAFT',
  customer: 10,
  invoiceType: 'GST',
  orderDate: '2026-09-01',
  expectedDelivery: '2026-09-10',
  paymentTermsDays: 15,
  notes,
  items: [
    {
      id: 71,
      product: 201,
      productName: 'Widget',
      quantity: '2',
      unitPrice: '100',
      gstRate: '18',
      cessRate: '0',
      discountPercent: '0',
    },
  ],
});

function mount(path: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <Link to="/sales/orders/6">open order 6</Link>
        <Routes>
          <Route path="/sales/orders/new" element={<SalesOrderEditorPage />} />
          <Route path="/sales/orders/:id" element={<SalesOrderEditorPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { qc, ...view };
}

const notesBox = () => screen.getByLabelText(t('billing.addNotes')) as HTMLTextAreaElement;

describe('SalesOrderEditorPage opening a saved order', () => {
  beforeEach(() => {
    api.getSalesOrder.mockReset();
    api.getProduct.mockReset();
  });

  it('fills the form and the lines from the saved order', async () => {
    api.getSalesOrder.mockResolvedValue(order('Deliver before Diwali'));
    mount('/sales/orders/5');
    await waitFor(() => expect(notesBox().value).toBe('Deliver before Diwali'));
    expect(await screen.findByText('Widget')).toBeTruthy();
    expect(await screen.findByDisplayValue('Anil Store')).toBeTruthy();
    expect(screen.getByDisplayValue('2026-09-01')).toBeTruthy();
    expect(screen.getByDisplayValue('2026-09-10')).toBeTruthy();
  });

  it('loads the order once, so a refresh does not overwrite what the user is typing', async () => {
    api.getSalesOrder.mockResolvedValue(order('Saved note'));
    const { qc } = mount('/sales/orders/5');
    await waitFor(() => expect(notesBox().value).toBe('Saved note'));

    fireEvent.change(notesBox(), { target: { value: 'My edit' } });
    api.getSalesOrder.mockResolvedValue(order('Changed on the server'));
    await qc.invalidateQueries({ queryKey: ['sales-orders', 5] });
    await waitFor(() => expect(api.getSalesOrder).toHaveBeenCalledTimes(2));

    expect(notesBox().value).toBe('My edit');
  });

  it('loads a different order when the address changes to another one', async () => {
    api.getSalesOrder.mockImplementation(async (id: number) => ({ ...order(`Note for ${id}`), id }));
    mount('/sales/orders/5');
    await waitFor(() => expect(notesBox().value).toBe('Note for 5'));

    fireEvent.click(screen.getByRole('link', { name: 'open order 6' }));
    await waitFor(() => expect(notesBox().value).toBe('Note for 6'));
  });
});

describe('SalesOrderEditorPage new order from a link', () => {
  beforeEach(() => {
    api.getSalesOrder.mockReset();
    api.getProduct.mockReset();
    api.getProduct.mockResolvedValue(WIDGET);
  });

  it('adds the product named in ?product= as the first line, once', async () => {
    mount('/sales/orders/new?product=201');
    expect(await screen.findByText('Widget')).toBeTruthy();
    await new Promise((resolve) => setTimeout(resolve, 200));
    expect(api.getProduct).toHaveBeenCalledTimes(1);
    expect(api.getProduct).toHaveBeenCalledWith(201);
    expect(screen.getAllByText('Widget')).toHaveLength(1);
  });

  it('selects the customer from ?customer= and then adds the product', async () => {
    mount('/sales/orders/new?customer=10&product=201');
    expect(await screen.findByDisplayValue('Anil Store')).toBeTruthy();
    expect(await screen.findByText('Widget')).toBeTruthy();
    expect(api.getProduct).toHaveBeenCalledTimes(1);
  });

  it('starts empty with no parameters', async () => {
    mount('/sales/orders/new');
    await screen.findByLabelText(t('billing.addNotes'));
    await new Promise((resolve) => setTimeout(resolve, 200));
    expect(api.getProduct).not.toHaveBeenCalled();
    expect(screen.queryByText('Widget')).toBeNull();
  });

  it('ignores a product link that is not a number', async () => {
    mount('/sales/orders/new?product=abc');
    await screen.findByLabelText(t('billing.addNotes'));
    await new Promise((resolve) => setTimeout(resolve, 200));
    expect(api.getProduct).not.toHaveBeenCalled();
  });

  it('does not stop the page working when the product link is stale', async () => {
    api.getProduct.mockRejectedValue(new Error('Not found'));
    mount('/sales/orders/new?product=999');
    await screen.findByLabelText(t('billing.addNotes'));
    await waitFor(() => expect(api.getProduct).toHaveBeenCalledTimes(1));
    expect(screen.queryByText('Widget')).toBeNull();
    expect(notesBox()).toBeTruthy();
  });
});
