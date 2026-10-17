import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AxiosError } from 'axios';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ExpiryAlertsPage } from '@/pages/inventory/ExpiryAlertsPage';

const getExpiryAlerts = vi.hoisted(() => vi.fn());
const writeOffExpiry = vi.hoisted(() => vi.fn());

vi.mock('@/api/resources', () => ({
  getExpiryAlerts: (...a: unknown[]) => getExpiryAlerts(...a),
  writeOffExpiry: (...a: unknown[]) => writeOffExpiry(...a),
  listWarehouses: async () => [{ id: 1, name: 'Main' }],
}));
vi.mock('@/hooks/useSubscriptionGate', () => ({ useSubscriptionGate: () => ({ writesBlocked: false }) }));

const row = (over: Record<string, unknown>) => ({
  product: 1, productName: 'Milk', batch: 11, batchNo: 'L1', warehouse: 1, warehouseName: 'Main',
  expiryDate: '2026-10-10', onHand: '10', reserved: '3', available: '7', unitCost: '20', value: '140.00',
  daysToExpiry: -6, expired: true, ...over,
});

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ExpiryAlertsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('ExpiryAlertsPage', () => {
  beforeEach(() => {
    getExpiryAlerts.mockReset();
    writeOffExpiry.mockReset();
    getExpiryAlerts.mockResolvedValue([
      row({}),
      row({ product: 2, productName: 'Curd', batch: 12, batchNo: 'C1', daysToExpiry: 4, expired: false, available: '5', onHand: '5', reserved: '0', value: '50.00', unitCost: '10' }),
    ]);
  });

  it('keeps lots that have already expired apart from ones about to, and says how long ago or how many days are left', async () => {
    const user = userEvent.setup();
    renderPage();
    expect(await screen.findByText('Milk')).toBeTruthy();
    expect(screen.queryByText('Curd')).toBeNull();
    expect(screen.getByText('Expired 6 days ago')).toBeTruthy();
    await user.click(screen.getByRole('tab', { name: /Expiring within 30 days \(1\)/ }));
    expect(await screen.findByText('Curd')).toBeTruthy();
    expect(screen.getByText('4 days left')).toBeTruthy();
  });

  it('shows what orders are holding and offers only what is free to write off', async () => {
    renderPage();
    const tr = (await screen.findByText('Milk')).closest('tr') as HTMLElement;
    expect(within(tr).getByText('3')).toBeTruthy(); // held
    expect(within(tr).getByText('7')).toBeTruthy(); // free
    expect(within(tr).getByText('₹140.00')).toBeTruthy();
  });

  it('writes a lot off with a reason, after showing the quantity and what it is worth', async () => {
    writeOffExpiry.mockResolvedValue({});
    const user = userEvent.setup();
    renderPage();
    const tr = (await screen.findByText('Milk')).closest('tr') as HTMLElement;
    await user.click(within(tr).getByRole('button', { name: 'Write off' }));
    const dialog = await screen.findByRole('dialog');
    expect((within(dialog).getByLabelText('Quantity') as HTMLInputElement).value).toBe('7');
    expect(within(dialog).getByText(/Written off at cost: ₹140.00/)).toBeTruthy();
    await user.click(within(dialog).getByRole('button', { name: 'Write off' }));
    await waitFor(() =>
      expect(writeOffExpiry).toHaveBeenCalledWith(
        { product: 1, warehouse: 1, batch: 11, quantity: 7, reason: 'EXPIRED' },
        { idempotencyKey: expect.any(String) },
      ),
    );
    expect(await screen.findByText('1 lots written off.')).toBeTruthy();
  });

  it('says a write-off is waiting for approval instead of calling it done', async () => {
    writeOffExpiry.mockResolvedValue({ status: 'PENDING', approvalId: 4 });
    const user = userEvent.setup();
    renderPage();
    const tr = (await screen.findByText('Milk')).closest('tr') as HTMLElement;
    await user.click(within(tr).getByRole('button', { name: 'Write off' }));
    const dialog = await screen.findByRole('dialog');
    await user.click(within(dialog).getByRole('button', { name: 'Write off' }));
    expect(await screen.findByText(/0 lots written off\./)).toBeTruthy();
    expect(await screen.findByText(/1 sent for approval/)).toBeTruthy();
  });

  it('offers sell-first only for stock that has not expired, and return-to-supplier for any free stock', async () => {
    const user = userEvent.setup();
    renderPage();
    const milk = (await screen.findByText('Milk')).closest('tr') as HTMLElement;
    expect(within(milk).queryByRole('link', { name: 'Sell first' })).toBeNull();
    expect(within(milk).getByRole('link', { name: 'Return to supplier' }).getAttribute('href')).toBe('/purchases/returns?create=1');
    await user.click(screen.getByRole('tab', { name: /Expiring within 30 days \(1\)/ }));
    const curd = (await screen.findByText('Curd')).closest('tr') as HTMLElement;
    expect(within(curd).getByRole('link', { name: 'Sell first' }).getAttribute('href')).toBe('/sales/quick-entry?product=2');
  });

  it('refuses a quantity above what is free', async () => {
    const user = userEvent.setup();
    renderPage();
    const tr = (await screen.findByText('Milk')).closest('tr') as HTMLElement;
    await user.click(within(tr).getByRole('button', { name: 'Write off' }));
    const dialog = await screen.findByRole('dialog');
    const qty = within(dialog).getByLabelText('Quantity');
    await user.clear(qty);
    await user.type(qty, '9');
    expect((within(dialog).getByRole('button', { name: 'Write off' }) as HTMLButtonElement).disabled).toBe(true);
    expect(within(dialog).getByText('Between 1 and 7')).toBeTruthy();
  });

  it('warns about stock that has not expired yet and suggests the damaged reason', async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole('tab', { name: /Expiring within 30 days \(1\)/ }));
    const tr = (await screen.findByText('Curd')).closest('tr') as HTMLElement;
    await user.click(within(tr).getByRole('button', { name: 'Write off' }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText(/have not expired yet/)).toBeTruthy();
    writeOffExpiry.mockResolvedValue({});
    await user.click(within(dialog).getByRole('button', { name: 'Write off' }));
    await waitFor(() => expect(writeOffExpiry).toHaveBeenCalledWith(expect.objectContaining({ reason: 'DAMAGED' }), expect.anything()));
  });

  it('writes off several lots at once and reports the ones that failed', async () => {
    getExpiryAlerts.mockResolvedValue([
      row({}),
      row({ product: 3, productName: 'Butter', batch: 13, batchNo: 'B1', available: '2', onHand: '2', reserved: '0', value: '40.00' }),
    ]);
    writeOffExpiry.mockResolvedValueOnce({}).mockRejectedValueOnce(new Error('Only 1 available'));
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole('checkbox', { name: 'Select every lot you can write off' }));
    await user.click(screen.getByRole('button', { name: 'Write off selected (2)' }));
    const dialog = await screen.findByRole('dialog');
    await user.click(within(dialog).getByRole('button', { name: 'Write off' }));
    await waitFor(() => expect(writeOffExpiry).toHaveBeenCalledTimes(2));
    expect(await screen.findAllByText(/Butter B1: Only 1 available/)).toBeTruthy();
  });

  it('does not repeat the lots that went through when the failed one is tried again', async () => {
    getExpiryAlerts.mockResolvedValue([
      row({}),
      row({ product: 3, productName: 'Butter', batch: 13, batchNo: 'B1', available: '2', onHand: '2', reserved: '0', value: '40.00' }),
    ]);
    const refused = new AxiosError('refused');
    refused.response = {
      status: 400, statusText: '', headers: {}, config: {} as never,
      data: { error: { code: 'business_rule_violation', message: 'Period is closed' } },
    };
    writeOffExpiry
      .mockResolvedValueOnce({})
      .mockRejectedValueOnce(refused)
      .mockResolvedValueOnce({});
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole('checkbox', { name: 'Select every lot you can write off' }));
    await user.click(screen.getByRole('button', { name: 'Write off selected (2)' }));
    const dialog = await screen.findByRole('dialog');
    await user.click(within(dialog).getByRole('button', { name: 'Write off' }));
    await waitFor(() => expect(writeOffExpiry).toHaveBeenCalledTimes(2));
    // Only the failed lot is left in the dialog.
    await waitFor(() => expect(within(dialog).queryByText(/Milk · L1/)).toBeNull());
    expect(within(dialog).getByText(/Butter · B1/)).toBeTruthy();
    await user.click(within(dialog).getByRole('button', { name: 'Write off' }));
    await waitFor(() => expect(writeOffExpiry).toHaveBeenCalledTimes(3));
    expect((writeOffExpiry.mock.calls[2][0] as { product: number }).product).toBe(3);
    // The refused lot was retried under a new key.
    const firstTry = (writeOffExpiry.mock.calls[1][1] as { idempotencyKey: string }).idempotencyKey;
    const retry = (writeOffExpiry.mock.calls[2][1] as { idempotencyKey: string }).idempotencyKey;
    expect(typeof retry).toBe('string');
    expect(retry).not.toBe(firstTry);
  });

  it('sends the return to the bill the lot came in on', async () => {
    getExpiryAlerts.mockResolvedValue([row({ purchaseInvoice: 88 })]);
    renderPage();
    const tr = (await screen.findByText('Milk')).closest('tr') as HTMLElement;
    expect(within(tr).getByRole('link', { name: 'Return to supplier' }).getAttribute('href')).toBe('/purchases/returns?purchase=88');
  });

  it('cannot write off a lot that is entirely held for orders', async () => {
    getExpiryAlerts.mockResolvedValue([row({ available: '0', reserved: '10' })]);
    renderPage();
    const tr = (await screen.findByText('Milk')).closest('tr') as HTMLElement;
    expect((within(tr).getByRole('button', { name: 'Write off' }) as HTMLButtonElement).disabled).toBe(true);
  });
});
