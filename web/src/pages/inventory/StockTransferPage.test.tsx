import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AxiosError } from 'axios';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { StockTransferPage } from '@/pages/inventory/StockTransferPage';

const listTransfers = vi.hoisted(() => vi.fn());
const completeTransfer = vi.hoisted(() => vi.fn());
const receiveTransfer = vi.hoisted(() => vi.fn());
const cancelTransfer = vi.hoisted(() => vi.fn());
const createTransfer = vi.hoisted(() => vi.fn());
const resolveTransferShortage = vi.hoisted(() => vi.fn());
const enqueueDraft = vi.hoisted(() => vi.fn());
const auth = vi.hoisted(() => ({ role: 'OWNER' }));

vi.mock('@/api/resources', () => ({
  listTransfers: () => listTransfers(),
  listWarehouses: async () => [
    { id: 1, name: 'Main', isActive: true },
    { id: 2, name: 'North', isActive: true },
  ],
  listStock: async () => [],
  listBatches: async () => [],
  getProduct: async () => ({ id: 8, name: 'Soap', sku: 'S' }),
  completeTransfer: (...a: unknown[]) => completeTransfer(...a),
  receiveTransfer: (...a: unknown[]) => receiveTransfer(...a),
  cancelTransfer: (...a: unknown[]) => cancelTransfer(...a),
  createTransfer: (...a: unknown[]) => createTransfer(...a),
  resolveTransferShortage: (...a: unknown[]) => resolveTransferShortage(...a),
}));
vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ user: { id: 1, companyId: 1, role: auth.role } }),
}));
vi.mock('@/hooks/useSubscriptionGate', () => ({ useSubscriptionGate: () => ({ writesBlocked: false }) }));
vi.mock('@/hooks/useActiveCustomFieldDefs', () => ({ useVisibleCustomFieldDefs: () => [] }));
vi.mock('@/hooks/useProductSearch', () => ({
  useProductSearch: () => ({
    productQuery: '', setProductQuery: () => undefined, options: [], isFetching: false,
    truncated: false, helperText: undefined, enabled: true, count: 0,
  }),
}));
const listDrafts = vi.hoisted(() => vi.fn());
vi.mock('@/offline/invoiceDraftCache', () => ({
  enqueueDraft: (...a: unknown[]) => enqueueDraft(...a),
  listDrafts: (...a: unknown[]) => listDrafts(...a),
}));
vi.mock('@/components/VirtualizedTable', () => ({
  VirtualizedTable: ({ children, rowCount }: { children: (a: unknown) => unknown; rowCount: number }) =>
    children({
      rows: Array.from({ length: rowCount }, (_, i) => ({ index: i, start: i * 52, end: (i + 1) * 52, size: 52, key: i })),
      totalSize: rowCount * 52,
      measureElement: () => undefined,
    }),
}));

const transfer = (over: Record<string, unknown>) => ({
  id: 5,
  number: 'TR-5',
  fromWarehouse: 1,
  toWarehouse: 2,
  fromWarehouseName: 'Main',
  toWarehouseName: 'North',
  status: 'DRAFT',
  notes: '',
  lines: [
    { id: 11, product: 8, productName: 'Soap', batch: null, batchNo: null, quantity: '5.000', shortageQty: '0.000', shortageReason: '' },
    { id: 12, product: 9, productName: 'Tea', batch: null, batchNo: null, quantity: '3.000', shortageQty: '0.000', shortageReason: '' },
  ],
  ...over,
});

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <StockTransferPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

/** Answers the in-app confirmation (the window.confirm replacement), checking what it says. */
async function answerConfirm(user: ReturnType<typeof userEvent.setup>, ok: boolean, text: string) {
  const dialog = await screen.findByRole('dialog', { name: 'Confirm' });
  expect(dialog.textContent).toContain(text);
  await user.click(within(dialog).getByRole('button', { name: ok ? 'Confirm' : 'Cancel' }));
  await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Confirm' })).toBeNull());
}

describe('StockTransferPage', () => {
  beforeEach(() => {
    for (const fn of [listTransfers, completeTransfer, receiveTransfer, cancelTransfer, createTransfer, enqueueDraft, resolveTransferShortage]) fn.mockReset();
    auth.role = 'OWNER';
    listDrafts.mockReset();
    listDrafts.mockResolvedValue([]);
  });
  afterEach(() => {
    vi.restoreAllMocks();
    Object.defineProperty(window.navigator, 'onLine', { value: true, configurable: true });
  });

  it('shows what is on each transfer and lets the user open its lines', async () => {
    listTransfers.mockResolvedValue([transfer({})]);
    const user = userEvent.setup();
    renderPage();
    expect(await screen.findByText('2 items · 8 units')).toBeTruthy();
    await user.click(screen.getByRole('button', { name: 'Details' }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText('Soap')).toBeTruthy();
    expect(within(dialog).getByText('Tea')).toBeTruthy();
  });

  it('lists goods in transit with their age and flags the late ones', async () => {
    const old = new Date(Date.now() - 5 * 86_400_000).toISOString();
    listTransfers.mockResolvedValue([transfer({ status: 'DISPATCHED', dispatchedAt: old })]);
    renderPage();
    expect(await screen.findByText('Goods in transit')).toBeTruthy();
    expect(screen.getByText('5 days on the road')).toBeTruthy();
    expect(screen.getByText('Late')).toBeTruthy();
  });

  it('shows missing goods and lets an owner write them off', async () => {
    listTransfers.mockResolvedValue([
      transfer({
        status: 'COMPLETED',
        lines: [{ id: 11, product: 8, productName: 'Soap', quantity: '5.000', shortageQty: '2.000', shortageReason: 'Broken', shortageResolution: '' }],
      }),
    ]);
    resolveTransferShortage.mockResolvedValue({ pendingApproval: false });
    const user = userEvent.setup();
    renderPage();
    expect(await screen.findByText('Soap: 2 missing (TR-5)')).toBeTruthy();
    await user.click(screen.getByRole('button', { name: 'Write off' }));
    await waitFor(() =>
      expect(resolveTransferShortage).toHaveBeenCalledWith(5, [{ line: 11, action: 'WRITE_OFF' }], { idempotencyKey: expect.any(String) }),
    );
    expect(await screen.findByText('Shortage settled.')).toBeTruthy();
  });

  it('does not offer to settle a shortage to a role that cannot', async () => {
    auth.role = 'INVENTORY_MANAGER';
    listTransfers.mockResolvedValue([
      transfer({
        status: 'COMPLETED',
        lines: [{ id: 11, product: 8, productName: 'Soap', quantity: '5.000', shortageQty: '2.000', shortageResolution: '' }],
      }),
    ]);
    renderPage();
    expect(await screen.findByText('Soap: 2 missing (TR-5)')).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Write off' })).toBeNull();
  });

  it('narrows the list by search text', async () => {
    listTransfers.mockResolvedValue([transfer({ id: 5, number: 'TR-5' }), transfer({ id: 6, number: 'TR-6', notes: 'festival stock' })]);
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('TR-5');
    await user.type(screen.getByLabelText('Search number, item or note'), 'festival');
    expect(screen.queryByText('TR-5')).toBeNull();
    expect(screen.getByText('TR-6')).toBeTruthy();
  });

  it('uses a new key for the retry after the server refused a dispatch', async () => {
    listTransfers.mockResolvedValue([transfer({})]);
    const refused = new AxiosError('refused');
    refused.response = {
      status: 400, statusText: '', headers: {}, config: {} as never,
      data: { error: { code: 'insufficient_stock', message: 'Insufficient stock' } },
    };
    completeTransfer.mockReset();
    completeTransfer.mockRejectedValueOnce(refused).mockResolvedValue({ status: 'DISPATCHED' });
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole('button', { name: 'Dispatch' }));
    await answerConfirm(user, true, 'Dispatch this transfer');
    await waitFor(() => expect(completeTransfer).toHaveBeenCalledTimes(1));
    await user.click(await screen.findByRole('button', { name: 'Dispatch' }));
    await answerConfirm(user, true, 'Dispatch this transfer');
    await waitFor(() => expect(completeTransfer).toHaveBeenCalledTimes(2));
    const first = (completeTransfer.mock.calls[0][1] as { idempotencyKey: string }).idempotencyKey;
    const second = (completeTransfer.mock.calls[1][1] as { idempotencyKey: string }).idempotencyKey;
    expect(second).not.toBe(first);
  });

  it('dispatches a draft after confirming, and can cancel it too', async () => {
    listTransfers.mockResolvedValue([transfer({})]);
    completeTransfer.mockResolvedValue({ status: 'DISPATCHED' });
    cancelTransfer.mockResolvedValue({ status: 'CANCELLED' });
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole('button', { name: 'Dispatch' }));
    await answerConfirm(user, true, 'Dispatch this transfer');
    await waitFor(() => expect(completeTransfer).toHaveBeenCalledWith(5, { idempotencyKey: expect.any(String) }));
    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    await answerConfirm(user, true, 'No stock has moved');
    await waitFor(() => expect(cancelTransfer).toHaveBeenCalledWith(5));
  });

  it('marks a transfer whose dispatch is waiting in the outbox as queued and hides its actions', async () => {
    listTransfers.mockResolvedValue([transfer({})]);
    listDrafts.mockResolvedValue([{ kind: 'stock_transfer', payload: { transferId: 5 } }]);
    renderPage();
    expect(await screen.findByText('Queued, waiting to send')).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Dispatch' })).toBeNull();
    expect(screen.getByRole('button', { name: 'Details' })).toBeTruthy();
  });

  it('offers receive and cancel on goods in transit', async () => {
    listTransfers.mockResolvedValue([transfer({ status: 'DISPATCHED' })]);
    renderPage();
    expect(await screen.findByRole('button', { name: 'Receive' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeTruthy();
  });

  it('records a short delivery: only the short line goes in receipts, with its reason', async () => {
    listTransfers.mockResolvedValue([transfer({ status: 'DISPATCHED' })]);
    receiveTransfer.mockResolvedValue({ status: 'COMPLETED' });
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole('button', { name: 'Receive' }));
    const dialog = await screen.findByRole('dialog');
    const [soapQty] = within(dialog).getAllByLabelText('Received');
    await user.clear(soapQty);
    await user.type(soapQty, '3');
    await user.type(await within(dialog).findByLabelText('Reason for the difference'), 'two broken');
    await user.click(within(dialog).getByRole('button', { name: 'Receive' }));
    await waitFor(() =>
      expect(receiveTransfer).toHaveBeenCalledWith(5, {
        idempotencyKey: expect.any(String),
        receipts: [{ line: 11, quantity: '3', reason: 'two broken' }],
      }),
    );
  });

  it('refuses a received quantity above what was sent', async () => {
    listTransfers.mockResolvedValue([transfer({ status: 'DISPATCHED' })]);
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole('button', { name: 'Receive' }));
    const dialog = await screen.findByRole('dialog');
    const [soapQty] = within(dialog).getAllByLabelText('Received');
    await user.clear(soapQty);
    await user.type(soapQty, '9');
    expect((within(dialog).getByRole('button', { name: 'Receive' }) as HTMLButtonElement).disabled).toBe(true);
  });

  it('lets an owner undo a received transfer but not a godown custodian', async () => {
    listTransfers.mockResolvedValue([transfer({ status: 'COMPLETED' })]);
    const view = renderPage();
    expect(await screen.findByRole('button', { name: 'Cancel' })).toBeTruthy();
    view.unmount();
    auth.role = 'SALES_STAFF';
    renderPage();
    await screen.findByText('TR-5');
    expect(screen.queryByRole('button', { name: 'Cancel' })).toBeNull();
  });

  it('says so when a dispatch was queued offline instead of leaving a silent draft', async () => {
    listTransfers.mockResolvedValue([transfer({})]);
    enqueueDraft.mockResolvedValue(undefined);
    Object.defineProperty(window.navigator, 'onLine', { value: false, configurable: true });
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole('button', { name: 'Dispatch' }));
    await answerConfirm(user, true, 'Dispatch this transfer');
    expect(await screen.findByText(/Saved on this device/)).toBeTruthy();
    expect(completeTransfer).not.toHaveBeenCalled();
  });

  it('shows the server warnings after a dispatch', async () => {
    listTransfers.mockResolvedValue([transfer({})]);
    completeTransfer.mockResolvedValue({ status: 'DISPATCHED', warnings: ['Soap goes negative at Main.'] });
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole('button', { name: 'Dispatch' }));
    await answerConfirm(user, true, 'Dispatch this transfer');
    expect(await screen.findByText('Soap goes negative at Main.')).toBeTruthy();
  });

  it('will not create a draft without an item and says why', async () => {
    listTransfers.mockResolvedValue([]);
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole('button', { name: 'New transfer' }));
    await user.click(await screen.findByRole('button', { name: 'Create draft' }));
    expect(createTransfer).not.toHaveBeenCalled();
    expect(await screen.findByText(/Choose a different destination godown|Choose an item/)).toBeTruthy();
  });
});
