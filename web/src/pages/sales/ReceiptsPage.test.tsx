import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import type { ReactElement } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { ReceiptsPage } from '@/pages/sales/ReceiptsPage';
import type { CustomerReceipt } from '@/types/domain';

const { RECEIPT, setReceiptChequeStatus, voidReceipt, trackShopFloor } = vi.hoisted(() => {
  const receipt: CustomerReceipt = {
    id: 44,
    number: 'RCT-0001',
    customer: 3,
    customerName: 'Ravi Traders',
    amount: '100.00',
    mode: 'CHEQUE',
    receiptDate: '2026-09-22',
    allocated: '0',
    unallocated: '100.00',
    status: 'POSTED',
    source: 'MANUAL',
    chequeNumber: '123456',
    chequeBankName: 'HDFC',
    chequeStatus: 'PENDING_CLEARANCE',
  };
  return {
    RECEIPT: receipt,
    setReceiptChequeStatus: vi.fn(async () => ({
      ...receipt,
      chequeStatus: 'CLEARED',
    })),
    voidReceipt: vi.fn(async () => ({
      ...receipt,
      status: 'VOID',
    })),
    trackShopFloor: vi.fn(),
  };
});

vi.mock('@/lib/telemetry', () => ({
  trackShopFloor: (...args: unknown[]) => trackShopFloor(...args),
}));

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 1, email: 'owner@x.test', fullName: 'Owner', role: 'OWNER', companyId: 9 },
  }),
}));

vi.mock('@/hooks/useSubscriptionGate', () => ({
  useSubscriptionGate: () => ({ writesBlocked: false, isLoading: false }),
}));

const listInvoices = vi.fn(async (_params?: unknown) => ({ results: [] as unknown[], count: 0, next: null, previous: null }));
const createAllocation = vi.fn(async (..._args: unknown[]) => ({}));

const listCustomersPage = vi.fn(async () => ({
  results: [
    { id: 10, name: 'Anil Store', phone: '9876543210', status: 'ACTIVE', outstanding: '500.00' },
  ],
  count: 1,
  next: null,
  previous: null,
}));

vi.mock('@/api/resources', () => ({
  listReceiptsPage: async () => ({ results: [RECEIPT], count: 1, next: null, previous: null }),
  listCustomersPage: (...args: unknown[]) => listCustomersPage(...(args as [])),
  listBankAccounts: async () => [],
  listSalesInvoicesPage: (params?: unknown) => listInvoices(params),
  createReceipt: vi.fn(),
  createAllocation: (...args: unknown[]) => createAllocation(...args),
  voidReceipt: (...args: unknown[]) => voidReceipt(...args),
  setReceiptChequeStatus: (...args: unknown[]) =>
    setReceiptChequeStatus(...(args as [number, string])),
}));

function wrap(ui: ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('ReceiptsPage cheque status', () => {
  it('clears a pending cheque from the row actions', async () => {
    wrap(<ReceiptsPage />);
    expect(await screen.findByText('RCT-0001')).toBeTruthy();
    expect(screen.getByText(/PENDING_CLEARANCE/)).toBeTruthy();
    await userEvent.click(screen.getByRole('button', { name: /mark cleared/i }));
    expect(setReceiptChequeStatus).toHaveBeenCalledWith(44, 'CLEARED');
  });

  it('triggers void receipt after user confirmation', async () => {
    wrap(<ReceiptsPage />);
    expect(await screen.findByText('RCT-0001')).toBeTruthy();
    const voidBtn = screen.getByRole('button', { name: /^void$/i });
    await userEvent.click(voidBtn);
    const dialog = await screen.findByRole('dialog');
    const confirmBtn = within(dialog).getByRole('button', { name: /^void$/i });
    await userEvent.click(confirmBtn);
    expect(voidReceipt).toHaveBeenCalledWith(44);
    expect(await screen.findByText('Receipt voided')).toBeTruthy();
    expect(trackShopFloor).toHaveBeenCalledWith('document_voided', { feature: 'form' });
  });

  it('pre-loads active customers when record receipt dialog opens without requiring 2 characters', async () => {
    wrap(<ReceiptsPage />);
    expect(await screen.findByText('RCT-0001')).toBeTruthy();
    const recordBtn = screen.getByRole('button', { name: /new receipt/i });
    await userEvent.click(recordBtn);
    expect(await screen.findByRole('dialog')).toBeTruthy();
    expect(listCustomersPage).toHaveBeenCalledWith(
      expect.objectContaining({ status: 'ACTIVE', pageSize: 50 }),
    );
  });
});

describe('ReceiptsPage allocating an advance', () => {
  const OPEN = (id: number, number: string, balance: string) => ({
    id,
    number,
    customer: 3,
    status: 'COMPLETED',
    balance,
    invoiceDate: '2026-09-01',
  });

  function mount() {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
    const invalidate = vi.spyOn(qc, 'invalidateQueries');
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <ReceiptsPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    return { invalidate };
  }

  async function openAllocateDialog() {
    expect(await screen.findByText('RCT-0001')).toBeTruthy();
    await userEvent.click(screen.getByRole('button', { name: /^allocate$/i }));
    return screen.findByRole('dialog');
  }

  it('lists only that customer bills that still owe money, and asks the server for them', async () => {
    listInvoices.mockResolvedValue({
      results: [OPEN(1, 'INV-1', '60.00'), OPEN(2, 'INV-2', '0'), OPEN(3, 'INV-3', '250.00')],
      count: 3,
      next: null,
      previous: null,
    });
    mount();
    const dialog = await openAllocateDialog();
    expect(await within(dialog).findByRole('button', { name: /INV-1/ })).toBeTruthy();
    expect(within(dialog).getByRole('button', { name: /INV-3/ })).toBeTruthy();
    expect(within(dialog).queryByRole('button', { name: /INV-2/ })).toBeNull();
    expect(listInvoices).toHaveBeenCalledWith(expect.objectContaining({ customer: 3, status: 'COMPLETED' }));
  });

  it('applies the smaller of the advance and the bill, then refreshes receipts and open bills', async () => {
    listInvoices.mockResolvedValue({ results: [OPEN(1, 'INV-1', '60.00')], count: 1, next: null, previous: null });
    createAllocation.mockClear();
    const { invalidate } = mount();
    const dialog = await openAllocateDialog();
    await userEvent.click(await within(dialog).findByRole('button', { name: /INV-1/ }));

    expect(createAllocation).toHaveBeenCalledTimes(1);
    expect(createAllocation.mock.calls[0][0]).toEqual({ receipt: 44, salesInvoice: 1, amount: 60 });
    expect(createAllocation.mock.calls[0][1]).toEqual({ idempotencyKey: expect.any(String) });

    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    const keys = invalidate.mock.calls.map((call) => JSON.stringify((call[0] as { queryKey: unknown }).queryKey));
    expect(keys).toContain(JSON.stringify(['receipts']));
    expect(keys).toContain(JSON.stringify(['sales-invoices-open']));
    expect(keys).toContain(JSON.stringify(['receipt-allocate-invoices']));
  });

  it('never applies more than the advance when the bill is larger', async () => {
    listInvoices.mockResolvedValue({ results: [OPEN(3, 'INV-3', '250.00')], count: 1, next: null, previous: null });
    createAllocation.mockClear();
    mount();
    const dialog = await openAllocateDialog();
    await userEvent.click(await within(dialog).findByRole('button', { name: /INV-3/ }));
    expect(createAllocation.mock.calls[0][0]).toEqual({ receipt: 44, salesInvoice: 3, amount: 100 });
  });

  it('keeps the dialog open and shows the problem when the allocation is refused', async () => {
    listInvoices.mockResolvedValue({ results: [OPEN(1, 'INV-1', '60.00')], count: 1, next: null, previous: null });
    createAllocation.mockRejectedValueOnce(new Error('Period is closed'));
    mount();
    const dialog = await openAllocateDialog();
    await userEvent.click(await within(dialog).findByRole('button', { name: /INV-1/ }));
    expect(await screen.findByText(/Period is closed/)).toBeTruthy();
    expect(screen.getByRole('dialog')).toBeTruthy();
  });
});
