import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { PurchaseOrdersPage } from '@/pages/purchases/PurchaseOrdersPage';

const api = vi.hoisted(() => ({
  listPurchaseOrdersPage: vi.fn(),
  convertPurchaseOrder: vi.fn(),
  cancelPurchaseOrder: vi.fn(),
}));

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ user: { id: 1, email: 'o@x.test', fullName: 'Owner', role: 'OWNER', companyId: 9 } }),
}));
vi.mock('@/api/resources', () => api);

function BillPage() {
  const state = useLocation().state as { message?: string } | null;
  return <div>bill page: {state?.message}</div>;
}

function setup(status: string) {
  api.listPurchaseOrdersPage.mockResolvedValue({
    count: 1,
    next: null,
    previous: null,
    results: [
      { id: 12, number: 'PO-12', orderDate: '2026-10-01', supplierName: 'Mega Suppliers', status, grandTotal: '500.00' },
    ],
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/purchases/orders']}>
        <Routes>
          <Route path="/purchases/orders" element={<PurchaseOrdersPage />} />
          <Route path="/purchases/history/:id" element={<BillPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => vi.clearAllMocks());

describe('PurchaseOrdersPage actions (WP-6)', () => {
  it('asks before converting and does nothing when declined', async () => {
    setup('DRAFT');
    await userEvent.click(await screen.findByRole('button', { name: /^create bill$/i }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText(/draft purchase bill from PO-12/i)).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole('button', { name: /^cancel$/i }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(api.convertPurchaseOrder).not.toHaveBeenCalled();
  });

  it('converts once confirmed and opens the bill that was created', async () => {
    setup('DRAFT');
    api.convertPurchaseOrder.mockResolvedValue({ id: 90, number: 'PUR-90' });
    await userEvent.click(await screen.findByRole('button', { name: /^create bill$/i }));
    await userEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: /^create bill$/i }));
    expect(await screen.findByText(/bill page: .*PUR-90 created from the order/)).toBeInTheDocument();
    expect(api.convertPurchaseOrder).toHaveBeenCalledTimes(1);
    expect(api.convertPurchaseOrder).toHaveBeenCalledWith(12);
  });

  it('keeps the list and shows the reason when converting is refused', async () => {
    setup('DRAFT');
    api.convertPurchaseOrder.mockRejectedValue(new Error('Order has no lines.'));
    await userEvent.click(await screen.findByRole('button', { name: /^create bill$/i }));
    await userEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: /^create bill$/i }));
    expect(await screen.findByText(/order has no lines/i)).toBeInTheDocument();
    expect(screen.queryByText(/bill page/)).not.toBeInTheDocument();
  });

  it('names the order in the cancel confirmation and reports it once cancelled', async () => {
    setup('COMPLETED');
    api.cancelPurchaseOrder.mockResolvedValue({ id: 12, number: 'PO-12' });
    await userEvent.click(await screen.findByRole('button', { name: /^cancel$/i }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText(/cancel purchase order PO-12/i)).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole('button', { name: /confirm cancel/i }));
    await waitFor(() => expect(api.cancelPurchaseOrder).toHaveBeenCalledWith(12));
    expect(await screen.findByText(/purchase order PO-12 cancelled/i)).toBeInTheDocument();
  });
});
