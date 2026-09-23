import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import type { ReactElement } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { CustomerLedgerPage } from '@/pages/reports/CustomerLedgerPage';

const downloadCustomerLedgerXlsx = vi.fn(async () => new Blob(['PK']));

vi.mock('@/api/resources', () => ({
  getCompany: async () => ({ id: 9, name: 'Shop', customFieldDefs: [] }),
  getCustomer: async () => ({ id: 3, name: 'Ravi Traders', phone: '9876543210', status: 'ACTIVE' }),
  getCustomerLedgerTabs: async () => ({
    customerId: 3,
    customerName: 'Ravi Traders',
    profile: { name: 'Ravi Traders', phone: '9876543210', shippingAddresses: [] },
    kpis: { totalReceivable: '100', overdueAmount: '0', totalSalesAmount: '100', totalReceivedAmount: '0' },
    transactions: [{ date: '2026-09-21', txnType: 'SALES', number: 'INV-1' }],
    statement: {
      outstanding: '50',
      entries: [
        { srNo: 1, date: '2026-09-21', type: 'RECEIPT', number: 'RCT-1', debit: '0', credit: '50', balance: '50', mode: 'CASH' },
      ],
    },
    itemWise: [],
  }),
  updateCustomer: vi.fn(),
  listCustomersPage: async () => ({
    results: [{ id: 3, name: 'Ravi Traders', phone: '9876543210', status: 'ACTIVE' }],
    count: 1,
    next: null,
    previous: null,
  }),
  downloadCustomerLedgerXlsx: (...args: unknown[]) => downloadCustomerLedgerXlsx(...(args as [])),
}));

vi.mock('@/utils/blob', () => ({
  triggerBlobDownload: vi.fn(),
}));

function wrap(ui: ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/reports/customer-ledger?customer=3']}>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('CustomerLedgerPage tabs and excel', () => {
  it('shows four ledger tabs and downloads excel', async () => {
    wrap(<CustomerLedgerPage />);
    expect(await screen.findByRole('tab', { name: /transactions/i })).toBeTruthy();
    expect(screen.getByRole('tab', { name: /profile/i })).toBeTruthy();
    expect(screen.getByRole('tab', { name: /item-wise/i })).toBeTruthy();
    expect(screen.getByRole('tab', { name: /statement/i })).toBeTruthy();
    await userEvent.click(screen.getByRole('button', { name: /download excel/i }));
    expect(downloadCustomerLedgerXlsx).toHaveBeenCalledWith(3, expect.any(Object));
  });

  it('shows payment status filter and statement payment mode', async () => {
    wrap(<CustomerLedgerPage />);
    expect(await screen.findByRole('tab', { name: /transactions/i })).toBeTruthy();
    expect(screen.getByLabelText(/^status$/i)).toBeTruthy();
    await userEvent.click(screen.getByRole('tab', { name: /statement/i }));
    expect(await screen.findByText('Sr No')).toBeTruthy();
    expect(screen.getByText('Payment mode')).toBeTruthy();
    expect(screen.getByText('CASH')).toBeTruthy();
  });
});
