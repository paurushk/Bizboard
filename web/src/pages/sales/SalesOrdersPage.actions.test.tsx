import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { SalesOrdersPage } from '@/pages/sales/SalesOrdersPage';

const state = vi.hoisted(() => ({ gates: false }));
const api = vi.hoisted(() => ({
  listSalesOrdersPage: vi.fn(),
  cancelSalesOrder: vi.fn(),
  convertSalesOrder: vi.fn(),
  convertSalesOrderToChallan: vi.fn(),
  confirmSalesOrder: vi.fn(),
}));

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 1, role: 'OWNER', companyId: 1, canCreateSales: true, canCancelDocuments: true },
  }),
}));
vi.mock('@/config/featureFlags', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/config/featureFlags')>();
  return {
    ...actual,
    isRuntimeFlagEnabled: (name: string) => (name === 'ENABLE_ORDER_GATES' ? state.gates : false),
    useFeatureFlagEpoch: () => 0,
  };
});
vi.mock('@/api/resources', () => ({
  listSalesOrdersPage: (...a: unknown[]) => api.listSalesOrdersPage(...a),
  convertSalesOrder: (...a: unknown[]) => api.convertSalesOrder(...a),
  convertSalesOrderToChallan: (...a: unknown[]) => api.convertSalesOrderToChallan(...a),
  cancelSalesOrder: (...a: unknown[]) => api.cancelSalesOrder(...a),
  createDeliveryRoute: vi.fn(),
  addOrdersToDeliveryRoute: vi.fn(),
}));
vi.mock('@/api/osPlan', () => ({
  checkSalesOrderGate: vi.fn(),
  confirmSalesOrder: (...a: unknown[]) => api.confirmSalesOrder(...a),
}));

const ORDERS = [
  { id: 1, number: 'SO-1', status: 'DRAFT', customerName: 'Draft Co', orderDate: '2026-10-01', grandTotal: '100' },
  { id: 2, number: 'SO-2', status: 'CONFIRMED', customerName: 'Confirmed Co', orderDate: '2026-10-01', grandTotal: '100' },
  { id: 3, number: 'SO-3', status: 'PARTIALLY_CONVERTED', customerName: 'Partly Co', orderDate: '2026-10-01', grandTotal: '100' },
  { id: 4, number: 'SO-4', status: 'CONVERTED', fulfilmentState: 'shipped_not_invoiced', customerName: 'Shipped Co', orderDate: '2026-10-01', grandTotal: '100' },
  { id: 5, number: 'SO-5', status: 'CONVERTED', fulfilmentState: 'invoiced', customerName: 'Billed Co', orderDate: '2026-10-01', grandTotal: '100' },
  { id: 6, number: 'SO-6', status: 'CANCELLED', customerName: 'Cancelled Co', orderDate: '2026-10-01', grandTotal: '100' },
];

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <SalesOrdersPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function rowFor(number: string) {
  return screen.getByText(number).closest('tr') as HTMLElement;
}

beforeEach(() => {
  state.gates = false;
  Object.values(api).forEach((fn) => fn.mockReset());
  api.listSalesOrdersPage.mockResolvedValue({ results: ORDERS, count: ORDERS.length, next: null, previous: null });
  api.cancelSalesOrder.mockResolvedValue({});
  api.confirmSalesOrder.mockResolvedValue({});
});

describe('SalesOrdersPage — every status has a way forward or says nothing (H-05, H-06, H-07)', () => {
  it('shows readable status labels, never the raw key, and "Shipped" for a shipped, unbilled order', async () => {
    renderPage();
    await screen.findByText('SO-1');
    expect(screen.queryByText(/status\.[A-Z_]+/)).toBeNull();
    expect(within(rowFor('SO-2')).getByText('Confirmed')).toBeInTheDocument();
    expect(within(rowFor('SO-3')).getByText('Partly processed')).toBeInTheDocument();
    expect(within(rowFor('SO-4')).getByText('Shipped')).toBeInTheDocument();
    expect(within(rowFor('SO-5')).getByText('Converted')).toBeInTheDocument();
  });

  it('order checks off: a draft can be confirmed, converted, or cancelled; once confirmed it can still be converted (the Quick Entry path)', async () => {
    renderPage();
    await screen.findByText('SO-1');
    const draft = within(rowFor('SO-1'));
    expect(draft.getByRole('button', { name: 'Confirm' })).toBeInTheDocument();
    expect(draft.getByRole('button', { name: 'Convert to challan' })).toBeInTheDocument();
    expect(draft.getByRole('button', { name: 'Convert to invoice' })).toBeInTheDocument();
    expect(draft.getByRole('button', { name: 'Cancel' })).toBeInTheDocument();

    const confirmed = within(rowFor('SO-2'));
    expect(confirmed.getByRole('button', { name: 'Convert to challan' })).toBeInTheDocument();
    expect(confirmed.getByRole('button', { name: 'Convert to invoice' })).toBeInTheDocument();
    expect(confirmed.getByRole('button', { name: 'Cancel' })).toBeInTheDocument();
    expect(confirmed.queryByRole('button', { name: 'Confirm' })).toBeNull();
  });

  it('order checks on: a draft must be confirmed first', async () => {
    state.gates = true;
    renderPage();
    await screen.findByText('SO-1');
    const draft = within(rowFor('SO-1'));
    expect(draft.getByRole('button', { name: 'Confirm' })).toBeInTheDocument();
    expect(draft.queryByRole('button', { name: 'Convert to invoice' })).toBeNull();
    expect(draft.queryByRole('button', { name: 'Convert to challan' })).toBeNull();
    expect(within(rowFor('SO-2')).getByRole('button', { name: 'Convert to invoice' })).toBeInTheDocument();
  });

  it('a partly processed order offers the remainder but no cancel; finished orders offer nothing', async () => {
    renderPage();
    await screen.findByText('SO-1');
    const partly = within(rowFor('SO-3'));
    expect(partly.getByRole('button', { name: 'Convert to invoice' })).toBeInTheDocument();
    expect(partly.queryByRole('button', { name: 'Cancel' })).toBeNull();
    for (const number of ['SO-4', 'SO-5', 'SO-6']) {
      expect(within(rowFor(number)).queryAllByRole('button')).toHaveLength(0);
    }
  });

  it('cancelling a confirmed order says the reserved stock will be released, then cancels once', async () => {
    renderPage();
    await screen.findByText('SO-2');
    fireEvent.click(within(rowFor('SO-2')).getByRole('button', { name: 'Cancel' }));
    expect(await screen.findByText(/stock reserved for it will be released/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Confirm cancel' }));
    await waitFor(() => expect(api.cancelSalesOrder).toHaveBeenCalledTimes(1));
    expect(api.cancelSalesOrder.mock.calls[0][0]).toBe(2);
  });

  it('cancelling a draft uses the plain wording', async () => {
    renderPage();
    await screen.findByText('SO-1');
    fireEvent.click(within(rowFor('SO-1')).getByRole('button', { name: 'Cancel' }));
    expect(await screen.findByText(/cannot be undone/i)).toBeInTheDocument();
    expect(screen.queryByText(/stock reserved for it/i)).toBeNull();
  });

  it('the Open filter asks for every order with something left to do; Closed asks for converted and cancelled', async () => {
    renderPage();
    await screen.findByText('SO-1');
    fireEvent.click(screen.getAllByText('Open')[0]);
    await waitFor(() =>
      expect(api.listSalesOrdersPage.mock.calls.some((c) => c[0]?.status === 'DRAFT,CONFIRMED,PARTIALLY_CONVERTED')).toBe(true),
    );
    fireEvent.click(screen.getAllByText('Closed')[0]);
    await waitFor(() =>
      expect(api.listSalesOrdersPage.mock.calls.some((c) => c[0]?.status === 'CONVERTED,CANCELLED')).toBe(true),
    );
  });
});
