import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import type { ReactElement } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { QuickEntryPage } from '@/pages/sales/QuickEntryPage';
import type { Customer, Product } from '@/types/domain';

const PRODUCT: Product = {
  id: 7,
  name: 'Widget',
  sku: 'WID-1',
  sellingPrice: '50',
  gstRate: '18',
} as Product;

const CUSTOMER: Customer = { id: 3, name: 'Ravi Traders' } as Customer;

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 1, email: 'rep@x.test', fullName: 'Rep', role: 'STAFF', canCreateSales: true, companyId: 9 },
  }),
}));

const createSalesInvoice = vi.fn(async (..._args: unknown[]) => ({ id: 555, status: 'DRAFT' }));

vi.mock('@/api/resources', () => ({
  createSalesInvoice: (...args: unknown[]) => createSalesInvoice(...args),
  listSalesInvoicesPage: async () => ({ results: [], count: 0, next: null, previous: null }),
}));

vi.mock('@/hooks/usePartySearch', () => ({
  useCustomerSearch: () => ({
    query: '',
    setQuery: vi.fn(),
    options: [CUSTOMER],
    isFetching: false,
    enabled: true,
  }),
}));

vi.mock('@/hooks/useProductSearch', () => ({
  useProductSearch: () => ({
    productQuery: '',
    setProductQuery: vi.fn(),
    options: [PRODUCT],
    isFetching: false,
    truncated: false,
    helperText: undefined,
    enabled: true,
    count: 1,
  }),
}));

const navigate = vi.fn();
vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>();
  return { ...actual, useNavigate: () => navigate };
});

function wrap(ui: ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('QuickEntryPage — QOS-0048', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it('requires a customer before Save order is enabled, even with items added', async () => {
    wrap(<QuickEntryPage />);
    const productInput = screen.getByLabelText(/search a product/i);
    fireEvent.mouseDown(productInput);
    fireEvent.change(productInput, { target: { value: 'Widget' } });
    fireEvent.click(await screen.findByText('Widget (WID-1)'));
    // Selecting adds the line immediately and clears the box for the next
    // scan — guards against the picked label getting stuck in the box.
    await waitFor(() => expect(productInput).toHaveValue(''));

    expect(await screen.findByText(/Pick a customer before saving/i)).toBeTruthy();
    expect(screen.getByRole('button', { name: /save order/i })).toBeDisabled();
  });

  it('tapping the quantity stepper twice makes 2 the line quantity, and Save posts both lines and items', async () => {
    wrap(<QuickEntryPage />);

    const customerInput = screen.getByLabelText(/search a customer/i);
    fireEvent.mouseDown(customerInput);
    fireEvent.change(customerInput, { target: { value: 'Ravi' } });
    fireEvent.click(await screen.findByText('Ravi Traders'));

    const productInput = screen.getByLabelText(/search a product/i);
    fireEvent.mouseDown(productInput);
    fireEvent.change(productInput, { target: { value: 'Widget' } });
    fireEvent.click(await screen.findByText('Widget (WID-1)'));

    fireEvent.click(await screen.findByLabelText(/increase quantity/i));
    await waitFor(() => expect(screen.getByText('2')).toBeTruthy());

    fireEvent.click(screen.getByRole('button', { name: /save order/i }));

    await waitFor(() => expect(createSalesInvoice).toHaveBeenCalledTimes(1));
    expect(createSalesInvoice).toHaveBeenCalledWith(
      expect.objectContaining({
        customer: 3,
        items: [expect.objectContaining({ product: 7, quantity: 2, unitPrice: 50 })],
      }),
    );
    await waitFor(() => expect(navigate).toHaveBeenCalledWith('/sales/history/555'));
  });

  it('adding a product a second time via a recent-SKU chip bumps its quantity instead of duplicating the line', async () => {
    wrap(<QuickEntryPage />);
    const productInput = screen.getByLabelText(/search a product/i);
    fireEvent.mouseDown(productInput);
    fireEvent.change(productInput, { target: { value: 'Widget' } });
    fireEvent.click(await screen.findByText('Widget (WID-1)'));
    await screen.findByText('1');

    // The just-added product is now a "recent" chip — tapping it again should
    // bump the existing line's quantity, not create a duplicate line.
    const chips = await screen.findAllByText('Widget');
    fireEvent.click(chips[0]);

    await waitFor(() => expect(screen.getByText('2')).toBeTruthy());
    expect(screen.getAllByText(/each$/i)).toHaveLength(1);
  });
});
