import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import type { ReactElement } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { SupplierPaymentsPage } from '@/pages/purchases/SupplierPaymentsPage';
import type { SupplierPayment } from '@/types/domain';

const { PAYMENT, setSupplierPaymentChequeStatus } = vi.hoisted(() => {
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
  };
});

vi.mock('@/api/resources', () => ({
  listSupplierPaymentsPage: async () => ({ results: [PAYMENT], count: 1, next: null, previous: null }),
  listSuppliers: async () => [],
  listAllPurchases: async () => [],
  createSupplierPayment: vi.fn(),
  createAllocation: vi.fn(),
  voidSupplierPayment: vi.fn(),
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
});
