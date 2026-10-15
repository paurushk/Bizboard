import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { GoodsReceiptsPage } from '@/pages/purchases/GoodsReceiptsPage';
import type { GoodsReceipt } from '@/api/legacy/purchases';

const mocks = vi.hoisted(() => ({
  listGoodsReceiptsPage: vi.fn(),
  createGoodsReceipt: vi.fn(),
  completeGoodsReceipt: vi.fn(),
  cancelGoodsReceipt: vi.fn(),
  deleteGoodsReceipt: vi.fn(),
  convertGoodsReceipt: vi.fn(),
  listSuppliersPage: vi.fn(),
  searchProducts: vi.fn(),
  listWarehouses: vi.fn(),
  listPurchaseOrders: vi.fn(),
}));

let role = 'OWNER';

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ user: { id: 1, email: 'o@x.test', fullName: 'Owner', role, companyId: 9 } }),
}));
vi.mock('@/api/legacy/purchases', () => ({
  listGoodsReceiptsPage: mocks.listGoodsReceiptsPage,
  createGoodsReceipt: mocks.createGoodsReceipt,
  completeGoodsReceipt: mocks.completeGoodsReceipt,
  cancelGoodsReceipt: mocks.cancelGoodsReceipt,
  deleteGoodsReceipt: mocks.deleteGoodsReceipt,
  convertGoodsReceipt: mocks.convertGoodsReceipt,
}));
vi.mock('@/api/resources', () => ({
  listSuppliersPage: mocks.listSuppliersPage,
  searchProducts: mocks.searchProducts,
  listWarehouses: mocks.listWarehouses,
  listPurchaseOrders: mocks.listPurchaseOrders,
}));

function grn(over: Partial<GoodsReceipt>): GoodsReceipt {
  return {
    id: 1,
    number: 'GRN-1',
    status: 'DRAFT',
    supplier: 7,
    supplierName: 'Mega Suppliers',
    receiptDate: '2026-10-10',
    items: [
      { product: 1, quantityReceived: '10', quantityAccepted: '8', quantityRejected: '2', unitPrice: '5' },
      { product: 2, quantityReceived: '4', quantityAccepted: '4', quantityRejected: '0', unitPrice: '9' },
    ],
    ...over,
  } as GoodsReceipt;
}

function setup(rows: GoodsReceipt[]) {
  mocks.listGoodsReceiptsPage.mockResolvedValue({ count: rows.length, next: null, previous: null, results: rows });
  mocks.listSuppliersPage.mockResolvedValue({
    count: 1,
    next: null,
    previous: null,
    results: [{ id: 7, name: 'Mega Suppliers' }],
  });
  mocks.listWarehouses.mockResolvedValue([{ id: 3, name: 'Main godown', code: 'M', isDefault: true }]);
  mocks.listPurchaseOrders.mockResolvedValue([]);
  mocks.searchProducts.mockResolvedValue([{ id: 1, name: 'Widget' }]);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/purchases/grns']}>
        <Routes>
          <Route path="/purchases/grns" element={<GoodsReceiptsPage />} />
          <Route path="/purchases/history/:id" element={<div>bill page</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  role = 'OWNER';
  vi.clearAllMocks();
});

describe('GoodsReceiptsPage', () => {
  it('shows an empty state that explains what a receipt does', async () => {
    setup([]);
    expect(await screen.findByText(/no goods receipts yet/i)).toBeInTheDocument();
    expect(screen.getByText(/adds the accepted quantity to stock/i)).toBeInTheDocument();
  });

  it('shows the status as a chip, not the raw code', async () => {
    setup([grn({ status: 'COMPLETED' })]);
    expect(await screen.findByText('GRN-1')).toBeInTheDocument();
    expect(screen.getByText('Completed')).toBeInTheDocument();
  });

  describe('completing a receipt', () => {
    it('asks first and names the units that will be added to stock', async () => {
      setup([grn({})]);
      await userEvent.click(await screen.findByRole('button', { name: /^complete$/i }));
      const dialog = await screen.findByRole('dialog');
      expect(within(dialog).getByText(/12 accepted unit\(s\) across 2 line\(s\)/)).toBeInTheDocument();
      expect(mocks.completeGoodsReceipt).not.toHaveBeenCalled();
    });

    it('does nothing when the dialog is dismissed', async () => {
      setup([grn({})]);
      await userEvent.click(await screen.findByRole('button', { name: /^complete$/i }));
      const dialog = await screen.findByRole('dialog');
      await userEvent.click(within(dialog).getByRole('button', { name: /^cancel$/i }));
      await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
      expect(mocks.completeGoodsReceipt).not.toHaveBeenCalled();
    });

    it('completes once, with an idempotency key, and says stock was updated', async () => {
      setup([grn({})]);
      mocks.completeGoodsReceipt.mockResolvedValue(grn({ status: 'COMPLETED' }));
      await userEvent.click(await screen.findByRole('button', { name: /^complete$/i }));
      const dialog = await screen.findByRole('dialog');
      await userEvent.click(within(dialog).getByRole('button', { name: /^complete$/i }));
      await waitFor(() => expect(mocks.completeGoodsReceipt).toHaveBeenCalledTimes(1));
      expect(mocks.completeGoodsReceipt.mock.calls[0][0]).toBe(1);
      expect(mocks.completeGoodsReceipt.mock.calls[0][1].idempotencyKey).toBeTruthy();
      expect(await screen.findByText(/receipt GRN-1 completed/i)).toBeInTheDocument();
    });

    it('shows the server reason when completing is refused', async () => {
      setup([grn({})]);
      mocks.completeGoodsReceipt.mockRejectedValue(new Error('A warehouse is required to receive goods into stock.'));
      await userEvent.click(await screen.findByRole('button', { name: /^complete$/i }));
      await userEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: /^complete$/i }));
      expect(await screen.findByText(/warehouse is required/i)).toBeInTheDocument();
    });
  });

  describe('cancelling and deleting a draft', () => {
    it('cancels after a confirmation', async () => {
      setup([grn({})]);
      mocks.cancelGoodsReceipt.mockResolvedValue(grn({ status: 'CANCELLED' }));
      await userEvent.click(await screen.findByRole('button', { name: /^cancel receipt$/i }));
      const dialog = await screen.findByRole('dialog');
      expect(within(dialog).getByText(/nothing has been added to stock/i)).toBeInTheDocument();
      await userEvent.click(within(dialog).getByRole('button', { name: /^cancel receipt$/i }));
      await waitFor(() => expect(mocks.cancelGoodsReceipt).toHaveBeenCalledTimes(1));
    });

    it('deletes after a confirmation', async () => {
      setup([grn({})]);
      mocks.deleteGoodsReceipt.mockResolvedValue(undefined);
      await userEvent.click(await screen.findByRole('button', { name: /^delete receipt$/i }));
      const dialog = await screen.findByRole('dialog');
      await userEvent.click(within(dialog).getByRole('button', { name: /^delete receipt$/i }));
      await waitFor(() => expect(mocks.deleteGoodsReceipt).toHaveBeenCalledTimes(1));
      expect(await screen.findByText(/draft receipt deleted/i)).toBeInTheDocument();
    });

    it('offers neither action on a completed receipt', async () => {
      setup([grn({ status: 'COMPLETED' })]);
      await screen.findByText('GRN-1');
      expect(screen.queryByRole('button', { name: /^cancel receipt$/i })).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /^delete receipt$/i })).not.toBeInTheDocument();
    });
  });

  describe('turning a completed receipt into a bill', () => {
    it('creates the draft bill and opens it', async () => {
      setup([grn({ status: 'COMPLETED' })]);
      mocks.convertGoodsReceipt.mockResolvedValue({ id: 55, number: null });
      await userEvent.click(await screen.findByRole('button', { name: /create bill/i }));
      await waitFor(() => expect(mocks.convertGoodsReceipt).toHaveBeenCalledTimes(1));
      expect(await screen.findByText('bill page')).toBeInTheDocument();
    });

    it('links to the bill that already exists instead of offering a second one', async () => {
      setup([grn({ status: 'COMPLETED', convertedPurchase: 55 })]);
      const link = await screen.findByRole('link', { name: /open bill/i });
      expect(link).toHaveAttribute('href', '/purchases/history/55');
      expect(screen.queryByRole('button', { name: /create bill/i })).not.toBeInTheDocument();
    });
  });

  describe('recording a new receipt', () => {
    async function pickSupplier() {
      const box = await screen.findByRole('combobox', { name: /supplier/i });
      await userEvent.click(box);
      await userEvent.click(await screen.findByRole('option', { name: 'Mega Suppliers' }));
    }

    it('searches suppliers on the server instead of listing only the first 50', async () => {
      setup([]);
      const box = await screen.findByRole('combobox', { name: /supplier/i });
      await userEvent.type(box, 'Meg');
      await waitFor(() =>
        expect(mocks.listSuppliersPage).toHaveBeenCalledWith(expect.objectContaining({ q: 'Meg' })),
      );
    });

    it('fills the lines from a purchase order of that supplier', async () => {
      setup([]);
      mocks.listPurchaseOrders.mockResolvedValue([
        {
          id: 40,
          number: 'PO-40',
          status: 'DRAFT',
          orderDate: '2026-10-01',
          items: [{ product: 1, productName: 'Widget', quantity: '12', unitPrice: '5' }],
        },
      ]);
      await pickSupplier();
      await waitFor(() => expect(mocks.listPurchaseOrders).toHaveBeenCalledWith({ supplier: '7' }));
      await userEvent.click(await screen.findByRole('combobox', { name: /against purchase order/i }));
      await userEvent.click(await screen.findByRole('option', { name: /PO-40/ }));
      expect(await screen.findByText(/lines filled from the order/i)).toBeInTheDocument();
      expect(screen.getAllByLabelText(/accepted/i)[0]).toHaveValue('12');
    });

    it('sends the purchase order and an idempotency key with the receipt', async () => {
      setup([]);
      mocks.listPurchaseOrders.mockResolvedValue([
        { id: 40, number: 'PO-40', status: 'DRAFT', orderDate: '2026-10-01', items: [{ product: 1, productName: 'Widget', quantity: '12', unitPrice: '5' }] },
      ]);
      mocks.createGoodsReceipt.mockResolvedValue(grn({}));
      await pickSupplier();
      await userEvent.click(await screen.findByRole('combobox', { name: /against purchase order/i }));
      await userEvent.click(await screen.findByRole('option', { name: /PO-40/ }));
      await userEvent.click(await screen.findByRole('button', { name: /create receipt/i }));
      await waitFor(() => expect(mocks.createGoodsReceipt).toHaveBeenCalledTimes(1));
      const [payload, opts] = mocks.createGoodsReceipt.mock.calls[0];
      expect(payload).toMatchObject({ supplier: 7, purchaseOrder: 40 });
      expect(payload.items[0]).toMatchObject({ product: 1, quantityAccepted: '12' });
      expect(opts.idempotencyKey).toBeTruthy();
    });

    it('lets a line be removed but never the last one', async () => {
      setup([]);
      await screen.findByRole('combobox', { name: /supplier/i });
      const remove = screen.getByRole('button', { name: /remove line/i });
      expect(remove).toBeDisabled();
      await userEvent.click(screen.getByRole('button', { name: /^add$/i }));
      await waitFor(() => expect(screen.getAllByRole('button', { name: /remove line/i })[0]).toBeEnabled());
    });
  });

  it('shows a read-only role the list but none of the write controls', async () => {
    role = 'VIEWER';
    setup([grn({})]);
    await screen.findByText('GRN-1');
    expect(screen.queryByRole('combobox', { name: /supplier/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^complete$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^delete receipt$/i })).not.toBeInTheDocument();
  });
});
