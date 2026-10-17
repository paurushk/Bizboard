import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AxiosError } from 'axios';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { PlanningLine } from '@/api/osPlan';
import { PurchasePlanningPage } from '@/pages/purchases/PurchasePlanningPage';

const getPurchasePlan = vi.hoisted(() => vi.fn());
const createPlanningDrafts = vi.hoisted(() => vi.fn());

vi.mock('@/api/osPlan', () => ({
  getPurchasePlan: (...a: unknown[]) => getPurchasePlan(...a),
  createPlanningDrafts: (...a: unknown[]) => createPlanningDrafts(...a),
}));
vi.mock('@/api/resources', () => ({ listWarehouses: async () => [{ id: 10, name: 'Main' }] }));
vi.mock('@/auth/AuthContext', () => ({ useAuth: () => ({ user: { id: 1, companyId: 1, role: 'OWNER' } }) }));
const mega = { id: 5, name: 'Mega Suppliers' };
vi.mock('@/hooks/usePartySearch', () => ({
  useSupplierSearch: () => ({ options: [mega], setQuery: () => undefined, isFetching: false }),
}));

const line = (over: Partial<PlanningLine> = {}): PlanningLine => ({
  productId: 1, productName: 'Tea', warehouseId: 10, warehouseName: 'Main', suggestedQty: '7',
  daysToStockout: 4, supplierId: 5, supplierName: 'Mega Suppliers', transferFromWarehouseId: null,
  transferFromWarehouseName: '', unit: 'pcs', scope: 'company', available: '3', reorderLevel: '10',
  onOrder: '0', lastPrice: '20', wholeUnitsOnly: true, ...over,
});

function renderPage(path = '/') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <PurchasePlanningPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('PurchasePlanningPage', () => {
  beforeEach(() => {
    getPurchasePlan.mockReset();
    createPlanningDrafts.mockReset();
  });

  it('shows what is low, what is already on order and who it would be bought from', async () => {
    getPurchasePlan.mockResolvedValue({
      rows: [line({ onOrder: '6' }), line({ productId: 2, productName: 'Rice', supplierId: null, supplierName: '', scope: 'godown' })],
      documents: [],
      coveredByOrders: 2,
    });
    renderPage();
    expect(await screen.findByText('Tea')).toBeTruthy();
    expect(screen.getByText('All godowns')).toBeTruthy();
    expect(screen.getAllByText('3 / 10')).toHaveLength(2);
    expect(screen.getByText('6')).toBeTruthy();
    expect(screen.getByText(/Mega Suppliers/)).toBeTruthy();
    expect(screen.getByText('No supplier yet')).toBeTruthy();
    expect(screen.getByText(/2 items are not listed because open purchase orders already cover them/)).toBeTruthy();
  });

  it('arrives from Low stock with every orderable row already ticked', async () => {
    getPurchasePlan.mockResolvedValue({
      rows: [line(), line({ productId: 2, productName: 'Rice' }), line({ productId: 3, productName: 'Oil', transferFromWarehouseId: 11, transferFromWarehouseName: 'North' })],
      documents: [],
    });
    renderPage('/inventory/purchase-planning?select=all');
    await screen.findByText('Tea');
    const boxes = screen.getAllByRole('checkbox') as HTMLInputElement[];
    const ticked = boxes.filter((b) => b.checked);
    expect(ticked.length).toBeGreaterThanOrEqual(2);
    const oil = (screen.getByText('Oil').closest('tr') as HTMLElement).querySelector('input[type=checkbox]') as HTMLInputElement;
    expect(oil.checked).toBe(false);
  });

  it('previews the orders and sends the edited quantity and supplier', async () => {
    getPurchasePlan.mockResolvedValue({ rows: [line()], documents: [] });
    createPlanningDrafts.mockResolvedValue({ purchaseOrderIds: [], needsSupplier: [] });
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole('checkbox', { name: 'Tea' }));
    const qty = screen.getByLabelText('Qty Tea');
    await user.clear(qty);
    await user.type(qty, '2.5');
    expect(screen.getByText('Ordered whole: 3')).toBeTruthy();
    await user.click(screen.getByRole('button', { name: 'Open draft' }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText(/Mega Suppliers: 1 lines, about/)).toBeTruthy();
    await user.click(within(dialog).getByRole('button', { name: 'Create drafts' }));
    await waitFor(() => expect(createPlanningDrafts).toHaveBeenCalledTimes(1));
    const [sent] = createPlanningDrafts.mock.calls[0];
    expect(sent).toHaveLength(1);
    expect(sent[0]).toMatchObject({ productId: 1, suggestedQty: '2.5', supplierId: 5 });
  });

  it('lets a supplier be chosen for rows that have none, then orders them', async () => {
    getPurchasePlan.mockResolvedValue({
      rows: [line({ productId: 2, productName: 'Rice', supplierId: null, supplierName: '' })],
      documents: [],
    });
    createPlanningDrafts.mockResolvedValue({ purchaseOrderIds: [], needsSupplier: [] });
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole('checkbox', { name: 'Rice' }));
    await user.click(screen.getByRole('button', { name: 'Open draft' }));
    let dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText(/1 rows have no supplier and will be left out/)).toBeTruthy();
    expect((within(dialog).getByRole('button', { name: 'Create drafts' }) as HTMLButtonElement).disabled).toBe(true);
    await user.click(within(dialog).getByRole('button', { name: 'Cancel' }));

    await user.click(await screen.findByRole('combobox', { name: 'Supplier for the selected rows' }));
    await user.click(await screen.findByRole('option', { name: 'Mega Suppliers' }));
    await user.click(screen.getByRole('button', { name: 'Apply' }));
    expect(screen.queryByText('No supplier yet')).toBeNull();

    await user.click(screen.getByRole('button', { name: 'Open draft' }));
    dialog = await screen.findByRole('dialog');
    await user.click(within(dialog).getByRole('button', { name: 'Create drafts' }));
    await waitFor(() => expect(createPlanningDrafts).toHaveBeenCalled());
    expect(createPlanningDrafts.mock.calls[0][0][0]).toMatchObject({ productId: 2, supplierId: 5 });
  });

  it('refuses a quantity of zero in the row and leaves it out of the order', async () => {
    getPurchasePlan.mockResolvedValue({ rows: [line()], documents: [] });
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole('checkbox', { name: 'Tea' }));
    const qty = screen.getByLabelText('Qty Tea');
    await user.clear(qty);
    await user.type(qty, '0');
    expect(screen.getByText('Enter a quantity greater than zero.')).toBeTruthy();
    await user.click(screen.getByRole('button', { name: 'Open draft' }));
    const dialog = await screen.findByRole('dialog');
    expect((within(dialog).getByRole('button', { name: 'Create drafts' }) as HTMLButtonElement).disabled).toBe(true);
  });

  it('explains a plan that is switched off instead of showing a bare error', async () => {
    const error = new AxiosError('bad', 'ERR_BAD_REQUEST', undefined, undefined, {
      status: 400, statusText: 'Bad', headers: {}, config: {} as never,
      data: { detail: 'Purchase planning needs replenishment turned on for this company.', code: 'replenishment_required' },
    });
    getPurchasePlan.mockRejectedValue(error);
    renderPage();
    expect(await screen.findByText(/needs replenishment switched on/)).toBeTruthy();
    expect(screen.queryByText(/Try again/i)).toBeNull();
  });

  it('no longer carries a forecast table of its own', async () => {
    getPurchasePlan.mockResolvedValue({ rows: [line()], documents: [] });
    renderPage();
    await screen.findByText('Tea');
    expect(screen.getByRole('link', { name: 'Demand forecast' }).getAttribute('href')).toBe('/inventory/demand-forecast');
    expect(screen.queryByText('Daily rate')).toBeNull();
  });
  it('keeps a transfer and a purchase for the same item as two separate rows', async () => {
    getPurchasePlan.mockResolvedValue({
      rows: [
        line({ productName: 'Rice', suggestedQty: '2', transferFromWarehouseId: 11, transferFromWarehouseName: 'North' }),
        line({ productName: 'Rice', suggestedQty: '6' }),
      ],
      documents: [],
    });
    const user = userEvent.setup();
    renderPage();
    const boxes = await screen.findAllByRole('checkbox', { name: 'Rice' });
    expect(boxes).toHaveLength(2);
    await user.click(boxes[1]);
    expect((boxes[0] as HTMLInputElement).checked).toBe(false);
    expect((boxes[1] as HTMLInputElement).checked).toBe(true);
  });

  it('says when old draft orders are being ignored', async () => {
    getPurchasePlan.mockResolvedValue({
      rows: [line()], documents: [], staleDrafts: [{ productId: 1, quantity: '50' }],
    });
    renderPage();
    expect(await screen.findByText(/1 items have old draft orders/)).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Open orders' }).getAttribute('href')).toBe('/purchases/orders');
  });

  it('sends a key with the drafts and asks before creating a duplicate', async () => {
    getPurchasePlan.mockResolvedValue({ rows: [line()], documents: [] });
    const duplicate = new AxiosError('refused');
    duplicate.response = {
      status: 400, statusText: '', headers: {}, config: {} as never,
      data: { error: { code: 'duplicate_draft', message: 'A draft was created in the last hour' } },
    };
    createPlanningDrafts.mockRejectedValueOnce(duplicate).mockResolvedValue({ purchaseOrderIds: [], needsSupplier: [] });
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole('checkbox', { name: 'Tea' }));
    await user.click(screen.getByRole('button', { name: 'Open draft' }));
    const dialog = await screen.findByRole('dialog');
    await user.click(within(dialog).getByRole('button', { name: 'Create drafts' }));
    await within(dialog).findByText(/created in the last hour/);
    expect(createPlanningDrafts.mock.calls[0][1]).toMatchObject({ idempotencyKey: expect.any(String), confirmDuplicate: false });
    await user.click(within(dialog).getByRole('button', { name: 'Create anyway' }));
    await waitFor(() => expect(createPlanningDrafts).toHaveBeenCalledTimes(2));
    expect(createPlanningDrafts.mock.calls[1][1]).toMatchObject({ confirmDuplicate: true });
    // The refused attempt's key is dropped, so the confirmed one is a new request.
    expect(createPlanningDrafts.mock.calls[1][1].idempotencyKey).not.toBe(createPlanningDrafts.mock.calls[0][1].idempotencyKey);
  });
});
