import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import type { ReactElement } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { SupplierPaymentsPage } from '@/pages/purchases/SupplierPaymentsPage';
import type { SupplierPayment } from '@/types/domain';

const {
  setSupplierPaymentChequeStatus,
  voidSupplierPayment,
  trackShopFloor,
  listSupplierPaymentsPage,
  getSupplierPaymentsSummary,
} = vi.hoisted(() => {
  const payment: SupplierPayment = {
    id: 71,
    number: 'PAY-0001',
    supplier: 4,
    supplierName: 'Mega Suppliers',
    amount: '80.00',
    mode: 'CHEQUE',
    paymentDate: '2026-09-22',
    allocated: '0',
    unallocated: '80.00',
    status: 'POSTED',
    chequeNumber: '778899',
    chequeBankName: 'Canara',
    chequeStatus: 'PENDING_CLEARANCE',
  };
  return {
    PAYMENT: payment,
    setSupplierPaymentChequeStatus: vi.fn(async () => ({
      ...payment,
      chequeStatus: 'CLEARED',
    })),
    voidSupplierPayment: vi.fn(async () => ({ ...payment, status: 'VOID' })),
    trackShopFloor: vi.fn(),
    listSupplierPaymentsPage: vi.fn(async () => ({ results: [payment], count: 1, next: null, previous: null })),
    getSupplierPaymentsSummary: vi.fn(async () => ({
      count: 1,
      paid: '0.00',
      chequesPending: '80.00',
      advance: '80.00',
      excludedCount: 2,
      payable: '1500.00',
      overdue: '400.00',
    })),
  };
});

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ user: { id: 1, role: 'OWNER', canViewFinancialReports: true, companyId: 9 } }),
}));

vi.mock('@/lib/telemetry', () => ({
  trackShopFloor: (...args: unknown[]) => trackShopFloor(...args),
}));

vi.mock('@/api/resources', () => ({
  listSupplierPaymentsPage: (...args: unknown[]) => listSupplierPaymentsPage(...args),
  getSupplierPaymentsSummary: (...args: unknown[]) => getSupplierPaymentsSummary(...args),
  listSuppliers: async () => [{ id: 4, name: 'Mega Suppliers', status: 'ACTIVE' }],
  listAllPurchases: async () => [
    { id: 501, number: 'PUR-1', supplier: 4, status: 'COMPLETED', grandTotal: '60.00', balance: '60.00' },
    { id: 502, number: 'PUR-2', supplier: 4, status: 'COMPLETED', grandTotal: '500.00', balance: '500.00' },
    { id: 503, number: 'PUR-3', supplier: 4, status: 'COMPLETED', grandTotal: '90.00', balance: '0' },
  ],
  createSupplierPayment: vi.fn(),
  createAllocation: vi.fn(),
  voidSupplierPayment: (...args: unknown[]) => voidSupplierPayment(...args),
  setSupplierPaymentChequeStatus: (...args: unknown[]) =>
    setSupplierPaymentChequeStatus(...(args as [number, string])),
}));

function wrap(ui: ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('SupplierPaymentsPage cheque status', () => {
  it('clears a pending supplier cheque from the row actions', async () => {
    wrap(<SupplierPaymentsPage />);
    expect(await screen.findByText('PAY-0001')).toBeTruthy();
    await userEvent.click(screen.getByRole('button', { name: /mark cleared/i }));
    expect(setSupplierPaymentChequeStatus).toHaveBeenCalledWith(71, 'CLEARED');
  });

  it('voids a payment and records that the document was voided', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    wrap(<SupplierPaymentsPage />);
    expect(await screen.findByText('PAY-0001')).toBeTruthy();
    await userEvent.click(screen.getByRole('button', { name: /^void$/i }));
    expect(voidSupplierPayment).toHaveBeenCalledWith(71);
    expect(await screen.findByText('Payment voided')).toBeTruthy();
    expect(trackShopFloor).toHaveBeenCalledWith('document_voided', { feature: 'form' });
  });
});

describe('SupplierPaymentsPage allocation amount', () => {
  async function openDialog() {
    wrap(<SupplierPaymentsPage />);
    expect(await screen.findByText('PAY-0001')).toBeTruthy();
    await userEvent.click(screen.getByRole('button', { name: /new payment|new supplier payment/i }));
    return screen.findByRole('dialog');
  }

  async function fillPayment(dialog: HTMLElement, amount: string) {
    await userEvent.click(within(dialog).getByRole('combobox', { name: /supplier/i }));
    await userEvent.click(await screen.findByRole('option', { name: /Mega Suppliers/ }));
    await userEvent.type(within(dialog).getByLabelText(/^amount/i), amount);
  }

  async function pickPurchase(dialog: HTMLElement, number: string) {
    await userEvent.click(within(dialog).getByRole('combobox', { name: /allocate to purchase/i }));
    await userEvent.click(await screen.findByRole('option', { name: new RegExp(number) }));
  }

  const allocateBox = (dialog: HTMLElement) => within(dialog).getByLabelText(/^allocate$/i) as HTMLInputElement;

  it('offers only bills that still have a balance', async () => {
    const dialog = await openDialog();
    await fillPayment(dialog, '100');
    await userEvent.click(within(dialog).getByRole('combobox', { name: /allocate to purchase/i }));
    expect(await screen.findByRole('option', { name: /PUR-1/ })).toBeTruthy();
    expect(screen.getByRole('option', { name: /PUR-2/ })).toBeTruthy();
    expect(screen.queryByRole('option', { name: /PUR-3/ })).toBeNull();
  });

  it('fills in the smaller of the payment and the bill balance', async () => {
    const dialog = await openDialog();
    await fillPayment(dialog, '100');
    await pickPurchase(dialog, 'PUR-1');
    await waitFor(() => expect(allocateBox(dialog).value).toBe('60'));
  });

  it('caps at the payment when the bill is bigger than what is being paid', async () => {
    const dialog = await openDialog();
    await fillPayment(dialog, '100');
    await pickPurchase(dialog, 'PUR-2');
    await waitFor(() => expect(allocateBox(dialog).value).toBe('100'));
  });

  it('follows the payment amount as it is changed after choosing the bill', async () => {
    const dialog = await openDialog();
    await fillPayment(dialog, '100');
    await pickPurchase(dialog, 'PUR-2');
    await waitFor(() => expect(allocateBox(dialog).value).toBe('100'));

    const amount = within(dialog).getByLabelText(/^amount/i);
    await userEvent.clear(amount);
    await userEvent.type(amount, '25');
    await waitFor(() => expect(allocateBox(dialog).value).toBe('25'));
  });

  it('keeps a figure the user typed while nothing it depends on changes', async () => {
    const dialog = await openDialog();
    await fillPayment(dialog, '100');
    await pickPurchase(dialog, 'PUR-1');
    const box = allocateBox(dialog);
    await userEvent.clear(box);
    await userEvent.type(box, '10');
    await new Promise((resolve) => setTimeout(resolve, 100));
    expect(allocateBox(dialog).value).toBe('10');
  });

  it('removes the allocation field when no bill is chosen', async () => {
    const dialog = await openDialog();
    await fillPayment(dialog, '100');
    expect(within(dialog).queryByLabelText(/^allocate$/i)).toBeNull();
  });
});

describe('SupplierPaymentsPage money strip and Money hub filters', () => {
  function wrapAt(url: string) {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
    return render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={[url]}>
          <SupplierPaymentsPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );
  }

  it('shows what is owed, overdue, paid, unapplied and waiting to clear', async () => {
    wrap(<SupplierPaymentsPage />);
    const group = await screen.findByRole('group', { name: /supplier payment totals/i });
    expect(within(group).getByText('You owe suppliers')).toBeTruthy();
    expect(within(group).getByText('₹1,500.00')).toBeTruthy();
    expect(within(group).getByText('₹400.00')).toBeTruthy();
    expect(within(group).getByText('Paid, not yet applied')).toBeTruthy();
    expect(screen.getByRole('link', { name: /see where you stand today/i })).toBeTruthy();
  });

  it('leaves out what is owed for someone who cannot see it', async () => {
    getSupplierPaymentsSummary.mockResolvedValueOnce({
      count: 1, paid: '0.00', chequesPending: '0.00', advance: '0.00', excludedCount: 0, payable: null, overdue: null,
    });
    wrap(<SupplierPaymentsPage />);
    const group = await screen.findByRole('group', { name: /supplier payment totals/i });
    expect(within(group).queryByText('You owe suppliers')).toBeNull();
    expect(within(group).getByText('Paid out')).toBeTruthy();
  });

  it('opens filtered when the Money hub sends cheques to clear, and sends the filter to the server', async () => {
    wrapAt('/purchases/payments?cheque_status=PENDING_CLEARANCE&via=money');
    expect(await screen.findByText(/opened from money: cheques issued, not cleared/i)).toBeTruthy();
    await waitFor(() =>
      expect(listSupplierPaymentsPage).toHaveBeenCalledWith(
        expect.objectContaining({ cheque_status: 'PENDING_CLEARANCE' }),
      ),
    );
    expect(getSupplierPaymentsSummary).toHaveBeenCalledWith(
      expect.objectContaining({ cheque_status: 'PENDING_CLEARANCE' }),
    );
    expect(screen.getByRole('link', { name: /back to money/i })).toBeTruthy();
  });

  it('opens on money not yet applied when the hub sends advances, and shows everything again on request', async () => {
    wrapAt('/purchases/payments?advance=1&via=money');
    expect(await screen.findByText(/opened from money: advances paid to suppliers/i)).toBeTruthy();
    await waitFor(() =>
      expect(listSupplierPaymentsPage).toHaveBeenCalledWith(expect.objectContaining({ advance: 'true' })),
    );
    await userEvent.click(screen.getByRole('button', { name: /show everything/i }));
    await waitFor(() => expect(screen.queryByText(/opened from money/i)).toBeNull());
    await waitFor(() =>
      expect(listSupplierPaymentsPage).toHaveBeenLastCalledWith(expect.not.objectContaining({ advance: 'true' })),
    );
  });

  it('shows a normal page, with no hand-off bar, when opened directly', async () => {
    wrap(<SupplierPaymentsPage />);
    await screen.findByText('PAY-0001');
    expect(screen.queryByText(/opened from money/i)).toBeNull();
  });
});
