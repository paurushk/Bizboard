import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AxiosError } from 'axios';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { StockAdjustmentPage } from '@/pages/inventory/StockAdjustmentPage';

const createStockAdjustment = vi.hoisted(() => vi.fn());
const listStock = vi.hoisted(() => vi.fn());
const getProduct = vi.hoisted(() => vi.fn());
const listBatches = vi.hoisted(() => vi.fn());

vi.mock('@/api/resources', () => ({
  createStockAdjustment: (...args: unknown[]) => createStockAdjustment(...args),
  listBatches: (...args: unknown[]) => listBatches(...args),
  getProduct: (...args: unknown[]) => getProduct(...args),
  listStock: (...args: unknown[]) => listStock(...args),
  listWarehouses: vi.fn().mockResolvedValue([{ id: 10, name: 'Main', isDefault: true, isActive: true }]),
}));

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ user: { id: 1, companyId: 1, role: 'OWNER', canAdjustInventory: true, company: {} } }),
}));
vi.mock('@/hooks/useActiveCustomFieldDefs', () => ({ useVisibleCustomFieldDefs: () => [] }));

const rice = { id: 1, name: 'Rice', sku: 'R1', unitName: 'KG', purchasePrice: '40', trackBatch: false };
vi.mock('@/hooks/useProductSearch', () => ({
  useProductSearch: () => ({
    options: [rice],
    isFetching: false,
    productQuery: '',
    setProductQuery: vi.fn(),
    helperText: '',
  }),
}));

function renderPage(path = '/') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <StockAdjustmentPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

async function pickRiceAndSave(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole('combobox', { name: /products/i }));
  await user.click(await screen.findByRole('option', { name: /Rice/ }));
  await user.click(screen.getByRole('button', { name: /^save$/i }));
}

describe('StockAdjustmentPage', () => {
  beforeEach(() => {
    createStockAdjustment.mockReset();
    getProduct.mockReset();
    listBatches.mockReset();
    listBatches.mockResolvedValue([]);
    listStock.mockReset();
    listStock.mockResolvedValue([
      { product: 1, warehouse: 10, productName: 'Rice', sku: 'R1', onHand: '12', reserved: '0', available: '12', reorderLevel: '0' },
    ]);
  });

  it('says an approval-pending adjustment is not recorded yet', async () => {
    createStockAdjustment.mockResolvedValue({ status: 'PENDING', approvalId: 7 });
    const user = userEvent.setup();
    renderPage();
    await pickRiceAndSave(user);
    expect(await screen.findByText(/Stock has not changed yet/)).toBeTruthy();
    expect(screen.queryByText('Stock adjustment recorded.')).toBeNull();
  });

  it('confirms an applied adjustment and carries the server warnings', async () => {
    createStockAdjustment.mockResolvedValue({ status: 'APPLIED', warnings: ['Stock at Main is now negative.'] });
    const user = userEvent.setup();
    renderPage();
    await pickRiceAndSave(user);
    expect(await screen.findByText(/Stock adjustment recorded\. Stock at Main is now negative\./)).toBeTruthy();
  });

  it('sends the typed fractional quantity, the date and one idempotency key per fill', async () => {
    createStockAdjustment.mockResolvedValue({ status: 'APPLIED' });
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole('combobox', { name: /products/i }));
    await user.click(await screen.findByRole('option', { name: /Rice/ }));
    const qty = screen.getByLabelText(/Quantity to Add/i);
    await user.clear(qty);
    await user.type(qty, '0.5');
    await user.click(screen.getByRole('button', { name: /^save$/i }));
    await waitFor(() => expect(createStockAdjustment).toHaveBeenCalledTimes(1));
    const [payload, options] = createStockAdjustment.mock.calls[0];
    expect(payload.quantity).toBe(0.5);
    expect(payload.reasonCode).toBe('COUNT_DIFFERENCE');
    expect(payload.date).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(typeof options.idempotencyKey).toBe('string');
    expect(options.idempotencyKey.length).toBeGreaterThan(8);
  });

  it('uses a new idempotency key for the resubmit after the server refused the adjustment', async () => {
    const refused = new AxiosError('refused');
    refused.response = {
      status: 400, statusText: '', headers: {}, config: {} as never,
      data: { error: { code: 'insufficient_stock', message: 'Insufficient stock' } },
    };
    createStockAdjustment.mockRejectedValueOnce(refused).mockResolvedValue({ status: 'APPLIED' });
    const user = userEvent.setup();
    renderPage();
    await pickRiceAndSave(user);
    await waitFor(() => expect(createStockAdjustment).toHaveBeenCalledTimes(1));
    await user.click(await screen.findByRole('button', { name: /^save$/i }));
    await waitFor(() => expect(createStockAdjustment).toHaveBeenCalledTimes(2));
    const first = createStockAdjustment.mock.calls[0][1].idempotencyKey;
    const second = createStockAdjustment.mock.calls[1][1].idempotencyKey;
    expect(second).not.toBe(first);
  });

  it('keeps the idempotency key when the response was lost, so a resubmit cannot post twice', async () => {
    createStockAdjustment.mockRejectedValueOnce(new AxiosError('Network Error', 'ERR_NETWORK')).mockResolvedValue({ status: 'APPLIED' });
    const user = userEvent.setup();
    renderPage();
    await pickRiceAndSave(user);
    await waitFor(() => expect(createStockAdjustment).toHaveBeenCalledTimes(1));
    await user.click(await screen.findByRole('button', { name: /^save$/i }));
    await waitFor(() => expect(createStockAdjustment).toHaveBeenCalledTimes(2));
    expect(createStockAdjustment.mock.calls[1][1].idempotencyKey).toBe(createStockAdjustment.mock.calls[0][1].idempotencyKey);
  });

  it('does not offer customer returns as an adjustment reason', async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole('combobox', { name: /Reason for Adjustment/i }));
    expect(screen.queryByRole('option', { name: /Customer Return/i })).toBeNull();
    expect(await screen.findByRole('option', { name: /Damaged/i })).toBeTruthy();
  });

  it('opens with the item, godown and reduce already chosen when launched from a stock row', async () => {
    getProduct.mockResolvedValue(rice);
    renderPage('/inventory/adjustments?product=1&warehouse=10&type=REDUCE');
    await waitFor(() => expect(getProduct).toHaveBeenCalledWith(1));
    expect(await screen.findByText('12 KG')).toBeTruthy();
    expect(screen.getByRole('button', { name: /reduce/i }).getAttribute('aria-pressed')).toBe('true');
  });

  it('picks the lot that expires first when reducing a batch item', async () => {
    getProduct.mockResolvedValue({ ...rice, trackBatch: true });
    listBatches.mockResolvedValue([
      { id: 31, productName: 'Rice', batchNo: 'LATE', expiryDate: '2027-06-01' },
      { id: 32, productName: 'Rice', batchNo: 'SOON', expiryDate: '2026-12-01' },
    ]);
    renderPage('/inventory/adjustments?product=1&warehouse=10&type=REDUCE');
    await waitFor(() => expect(listBatches).toHaveBeenCalledWith(1, 10));
    await waitFor(() => expect(screen.getByRole('combobox', { name: /existing batch/i }).textContent).toContain('SOON'));
  });
});
