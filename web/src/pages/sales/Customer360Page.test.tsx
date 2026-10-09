import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { Customer360Page } from '@/pages/sales/Customer360Page';

vi.mock('@/api/osPlan', () => ({
  getCustomer360: vi.fn().mockResolvedValue({
    customerId: 4,
    name: 'Ravi Traders',
    sales: { invoices: 2, amount: '100' },
    products: ['Repeat Soap'],
    pattern: 'on_time',
    recommendedNextStep: '',
    outstanding: '40',
    aging: { current: '10', '130': '20', '3160': '0', '6190': '0', '90Plus': '5' },
    profit: { totals: { margin: '15', revenue: '100', cogs: '85' } },
  }),
}));

const listPaymentPromises = vi.fn(async () => [] as Array<Record<string, unknown>>);
const createPaymentPromise = vi.fn(async (payload: Record<string, unknown>) => ({
  id: 99,
  resolved: false,
  ...payload,
}));
const resolvePaymentPromise = vi.fn(async (id: number) => ({ id, resolved: true }));

vi.mock('@/api/resources', () => ({
  repeatLastInvoice: vi.fn(),
  listSalesInvoicesPage: async () => ({ results: [], count: 0, next: null, previous: null }),
  listPaymentPromises: () => listPaymentPromises(),
  createPaymentPromise: (payload: Record<string, unknown>) => createPaymentPromise(payload),
  resolvePaymentPromise: (id: number) => resolvePaymentPromise(id),
}));

// F2-050 pattern (see InvoiceDetailPage.test.tsx): OWNER is the default
// identity here; individual tests swap `currentUser` for the duration of one
// test and the afterEach restores it.
const OWNER_USER = { id: 1, email: 'owner@x.test', fullName: 'Owner', role: 'OWNER', companyId: 9 };
const SALES_STAFF_USER = { id: 2, email: 'staff@x.test', fullName: 'Staff', role: 'SALES_STAFF', companyId: 9 };
let currentUser: Record<string, unknown> = OWNER_USER;

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ user: currentUser }),
}));

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/sales/customers/4']}>
        <Routes>
          <Route path="/sales/customers/:id" element={<Customer360Page />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('Customer360Page', () => {
  afterEach(() => {
    currentUser = OWNER_USER;
    listPaymentPromises.mockReset();
    listPaymentPromises.mockResolvedValue([]);
    createPaymentPromise.mockClear();
    resolvePaymentPromise.mockClear();
  });

  it('shows aging buckets and profit from the margin total', async () => {
    renderPage();
    expect(await screen.findByText('Ravi Traders')).toBeInTheDocument();
    expect(screen.getByText(/Profit:/)).toHaveTextContent('15.00');
    expect(screen.getByText(/Not yet due:/)).toHaveTextContent('10.00');
    expect(screen.getByText(/1–30 days:/)).toHaveTextContent('20.00');
    expect(screen.getByText(/Over 90 days:/)).toHaveTextContent('5.00');
    expect(screen.getByText('Repeat Soap')).toBeInTheDocument();
  });

  describe('payment promises', () => {
    it('shows this customer’s open promises, filtering out other customers’', async () => {
      listPaymentPromises.mockResolvedValueOnce([
        { id: 5, customer: 4, promisedDate: '2026-10-01', resolved: false, note: 'Will pay after harvest' },
        { id: 6, customer: 999, promisedDate: '2026-10-05', resolved: false },
      ]);
      renderPage();

      expect(await screen.findByText(/2026-10-01/)).toBeInTheDocument();
      expect(screen.getByText('Will pay after harvest')).toBeInTheDocument();
      expect(screen.queryByText(/2026-10-05/)).not.toBeInTheDocument();
    });

    it('shows a sensible empty state when there are no open promises', async () => {
      listPaymentPromises.mockResolvedValueOnce([]);
      renderPage();
      expect(await screen.findByText('Ravi Traders')).toBeInTheDocument();
      expect(
        await screen.findByText('No open payment promises for this customer.'),
      ).toBeInTheDocument();
    });

    it('lets an OWNER/MANAGER/ACCOUNTANT create a promise from the form', async () => {
      listPaymentPromises.mockResolvedValueOnce([]);
      renderPage();
      await screen.findByText('Ravi Traders');

      const logBtn = await screen.findByRole('button', { name: /log a promise to pay/i });
      await userEvent.click(logBtn);

      const dialog = await screen.findByRole('dialog', { name: /log a promise to pay/i });
      fireEvent.change(within(dialog).getByLabelText(/promised date/i), {
        target: { value: '2026-10-05' },
      });
      fireEvent.change(within(dialog).getByLabelText(/promised amount/i), {
        target: { value: '500' },
      });
      await userEvent.type(within(dialog).getByLabelText(/note/i), 'Will pay after collections');
      await userEvent.click(within(dialog).getByRole('button', { name: /save promise/i }));

      expect(createPaymentPromise).toHaveBeenCalledWith(
        expect.objectContaining({
          customer: 4,
          promisedDate: '2026-10-05',
          promisedAmount: '500',
          note: 'Will pay after collections',
        }),
      );
    });

    it('lets an OWNER/MANAGER/ACCOUNTANT resolve an existing open promise', async () => {
      listPaymentPromises.mockResolvedValueOnce([
        { id: 55, customer: 4, promisedDate: '2026-10-01', note: 'Paying next week', resolved: false },
      ]);
      renderPage();

      expect(await screen.findByText(/2026-10-01/)).toBeInTheDocument();
      await userEvent.click(screen.getByRole('button', { name: /mark as resolved/i }));
      expect(resolvePaymentPromise).toHaveBeenCalledWith(55);
    });

    it('hides create/resolve controls for a role without manage permission', async () => {
      currentUser = SALES_STAFF_USER;
      listPaymentPromises.mockResolvedValueOnce([
        { id: 55, customer: 4, promisedDate: '2026-10-01', note: 'Paying next week', resolved: false },
      ]);
      renderPage();

      // The list itself still renders, read-only.
      expect(await screen.findByText(/2026-10-01/)).toBeInTheDocument();
      expect(screen.getByText('Paying next week')).toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /log a promise to pay/i })).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /mark as resolved/i })).not.toBeInTheDocument();
    });
  });
});
