import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { configure, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Link, MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { PurchaseOrderEditorPage } from '@/pages/purchases/PurchaseOrderEditorPage';
import { t } from '@/i18n';

configure({ asyncUtilTimeout: 15_000 });
vi.setConfig({ testTimeout: 40_000 });

const api = vi.hoisted(() => ({
  getPurchaseOrder: vi.fn(),
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

vi.mock('@/api/resources', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/resources')>();
  return {
    ...actual,
    getCompany: async () => ({ id: 9, name: 'Acme', registrationType: 'REGULAR', state: 'Delhi', gstin: '07AAAAA0000A1Z5' }),
    getSupplier: async (id: number) => ({ id, name: `Supplier ${id}`, status: 'ACTIVE', state: 'Delhi' }),
    listSuppliersPage: async () => ({
      results: [
        { id: 31, name: 'Supplier 31', status: 'ACTIVE', state: 'Delhi' },
        { id: 32, name: 'Supplier 32', status: 'ACTIVE', state: 'Delhi' },
      ],
      count: 2,
      next: null,
      previous: null,
    }),
    listProductsPage: async () => ({ results: [], count: 0, next: null, previous: null }),
    searchProducts: async () => [],
    listCustomFieldDefinitions: async () => [],
    fetchSupplierNudge: async () => ({ rows: [] }),
    getPurchaseOrder: (...args: unknown[]) => api.getPurchaseOrder(...args),
    getProduct: (...args: unknown[]) => api.getProduct(...args),
  };
});

const WIDGET = { id: 201, name: 'Widget', sku: 'WID-1', purchasePrice: 60, unitName: 'PCS', status: 'ACTIVE', gstRate: 18 };

const order = (notes: string, id = 5) => ({
  id,
  status: 'DRAFT',
  supplier: 31,
  purchaseType: 'GST',
  orderDate: '2026-09-01',
  expectedDelivery: '2026-09-12',
  notes,
  items: [
    { id: 81, product: 201, productName: 'Widget', quantity: '3', unitPrice: '60', gstRate: '18', cessRate: '0' },
  ],
});

function mount(path: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <Link to="/purchases/orders/6">open order 6</Link>
        <Routes>
          <Route path="/purchases/orders/new" element={<PurchaseOrderEditorPage />} />
          <Route path="/purchases/orders/:id" element={<PurchaseOrderEditorPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { qc, ...view };
}

const notesBox = () => screen.getByLabelText(t('billing.addNotes')) as HTMLTextAreaElement;

describe('PurchaseOrderEditorPage opening a saved order', () => {
  beforeEach(() => {
    api.getPurchaseOrder.mockReset();
    api.getProduct.mockReset();
  });

  it('fills the form and the lines from the saved order', async () => {
    api.getPurchaseOrder.mockResolvedValue(order('Pay on delivery'));
    mount('/purchases/orders/5');
    await waitFor(() => expect(notesBox().value).toBe('Pay on delivery'));
    expect(await screen.findByText('Widget')).toBeTruthy();
    expect(await screen.findByDisplayValue('Supplier 31')).toBeTruthy();
    expect(screen.getByDisplayValue('2026-09-12')).toBeTruthy();
  });

  it('loads the order once, so a refresh does not overwrite what the user is typing', async () => {
    api.getPurchaseOrder.mockResolvedValue(order('Saved note'));
    const { qc } = mount('/purchases/orders/5');
    await waitFor(() => expect(notesBox().value).toBe('Saved note'));

    fireEvent.change(notesBox(), { target: { value: 'My edit' } });
    api.getPurchaseOrder.mockResolvedValue(order('Changed on the server'));
    await qc.invalidateQueries({ queryKey: ['purchase-orders', 5] });
    await waitFor(() => expect(api.getPurchaseOrder).toHaveBeenCalledTimes(2));

    expect(notesBox().value).toBe('My edit');
  });

  it('loads a different order when the address changes to another one', async () => {
    api.getPurchaseOrder.mockImplementation(async (id: number) => order(`Note for ${id}`, id));
    mount('/purchases/orders/5');
    await waitFor(() => expect(notesBox().value).toBe('Note for 5'));
    fireEvent.click(screen.getByRole('link', { name: 'open order 6' }));
    await waitFor(() => expect(notesBox().value).toBe('Note for 6'));
  });
});

describe('PurchaseOrderEditorPage new order from a link', () => {
  beforeEach(() => {
    api.getPurchaseOrder.mockReset();
    api.getProduct.mockReset();
    api.getProduct.mockResolvedValue(WIDGET);
  });

  it('selects the supplier named in ?supplier=', async () => {
    mount('/purchases/orders/new?supplier=31');
    expect(await screen.findByDisplayValue('Supplier 31')).toBeTruthy();
  });

  it('lets the user choose a different supplier after the link filled one in', async () => {
    const user = userEvent.setup();
    mount('/purchases/orders/new?supplier=31');
    const box = (await screen.findByDisplayValue('Supplier 31')) as HTMLInputElement;

    await user.click(box);
    await user.click(await screen.findByRole('option', { name: /Supplier 32/ }));
    await waitFor(() => expect(box.value).toBe('Supplier 32'));

    // Later renders (the supplier lookups settling, typing elsewhere) must not put the link's supplier back.
    fireEvent.change(notesBox(), { target: { value: 'typing elsewhere' } });
    await new Promise((resolve) => setTimeout(resolve, 400));
    expect(box.value).toBe('Supplier 32');
  });

  it('adds the product named in ?product= with the quantity from ?qty=', async () => {
    mount('/purchases/orders/new?product=201&qty=4');
    expect(await screen.findByText('Widget')).toBeTruthy();
    expect(await screen.findByDisplayValue('4')).toBeTruthy();
    expect(api.getProduct).toHaveBeenCalledWith('201');
  });

  it('adds every line from ?lines= with its quantity', async () => {
    api.getProduct.mockImplementation(async (id: number) => ({ ...WIDGET, id, name: `Item ${id}` }));
    const lines = encodeURIComponent(JSON.stringify([{ productId: 11, qty: '2' }, { productId: 12, qty: '5' }]));
    mount(`/purchases/orders/new?lines=${lines}`);
    expect(await screen.findByText('Item 11')).toBeTruthy();
    expect(await screen.findByText('Item 12')).toBeTruthy();
    expect(screen.getByDisplayValue('5')).toBeTruthy();
  });

  it('keeps a lines link that cannot be read from breaking the page', async () => {
    mount('/purchases/orders/new?lines=%7Bnot-json');
    await screen.findByLabelText(t('billing.addNotes'));
    expect(api.getProduct).not.toHaveBeenCalled();
  });

  it('starts empty with no parameters', async () => {
    mount('/purchases/orders/new');
    await screen.findByLabelText(t('billing.addNotes'));
    await new Promise((resolve) => setTimeout(resolve, 200));
    expect(api.getProduct).not.toHaveBeenCalled();
    expect(screen.queryByText('Widget')).toBeNull();
  });
});
