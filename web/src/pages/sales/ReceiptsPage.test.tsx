import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import type { ReactElement } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { ReceiptsPage } from '@/pages/sales/ReceiptsPage';
import type { CustomerReceipt } from '@/types/domain';

const { RECEIPT, setReceiptChequeStatus } = vi.hoisted(() => {
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
  };
});

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 1, email: 'owner@x.test', fullName: 'Owner', role: 'OWNER', companyId: 9 },
  }),
}));

vi.mock('@/hooks/useSubscriptionGate', () => ({
  useSubscriptionGate: () => ({ writesBlocked: false, isLoading: false }),
}));

vi.mock('@/api/resources', () => ({
  listReceiptsPage: async () => ({ results: [RECEIPT], count: 1, next: null, previous: null }),
  listCustomersPage: async () => ({ results: [], count: 0, next: null, previous: null }),
  listBankAccounts: async () => [],
  listSalesInvoicesPage: async () => ({ results: [], count: 0, next: null, previous: null }),
  createReceipt: vi.fn(),
  createAllocation: vi.fn(),
  voidReceipt: vi.fn(),
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
});
