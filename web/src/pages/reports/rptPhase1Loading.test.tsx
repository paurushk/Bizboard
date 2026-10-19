import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { CashBookPage } from '@/pages/phase/BankingPhasePages';
import { StockValuationPage } from '@/pages/reports/StockValuationPage';

const { getCashBook, getStockValuation, auth } = vi.hoisted(() => ({
  getCashBook: vi.fn(),
  getStockValuation: vi.fn(),
  auth: { role: 'ACCOUNTANT', canExport: false },
}));

vi.mock('@/api/resources', async () => {
  const actual = await vi.importActual<typeof import('@/api/resources')>('@/api/resources');
  return {
    ...actual,
    getCashBook: (...a: unknown[]) => getCashBook(...a),
    getPaymentHealth: async () => ({ alerts: [], summary: {} }),
    downloadCashBookXlsx: vi.fn(),
    listWarehouses: async () => [],
    listBankAccounts: async () => [{ id: 3, name: 'HDFC Current' }],
    getStockValuation: (...a: unknown[]) => getStockValuation(...a),
  };
});
vi.mock('@/components/VirtualizedTable', () => ({
  VirtualizedTable: ({ rowCount, children }: { rowCount?: number; children: (a: { rows: { index: number; start: number; end: number; size: number }[]; totalSize: number; measureElement: () => void }) => ReactNode }) =>
    children({ rows: Array.from({ length: rowCount ?? 0 }, (_, index) => ({ index, start: index * 52, end: (index + 1) * 52, size: 52 })), totalSize: 0, measureElement: () => {} }),
}));
vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ user: { id: 1, email: 'a@x.test', fullName: 'A', role: auth.role, canExport: auth.canExport, canCreatePayments: true, companyId: 9 } }),
}));

function wrap(node: JSX.Element) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{node}</MemoryRouter>
    </QueryClientProvider>,
  );
}

const CASH = { opening: '0', inflow: '100', outflow: '0', closing: '100', rows: [], disclaimer: 'docs' };

beforeEach(() => {
  vi.clearAllMocks();
  auth.role = 'ACCOUNTANT';
  auth.canExport = false;
});

describe('RPT-05 / RPT-09 Cash Book', () => {
  it('keeps the date boxes and the last result while a new range loads', async () => {
    getCashBook.mockResolvedValueOnce(CASH);
    wrap(<CashBookPage />);
    await screen.findByText('Opening');
    getCashBook.mockReturnValue(new Promise(() => {})); // never resolves
    const from = screen.getAllByLabelText(/from/i)[0] as HTMLInputElement;
    fireEvent.change(from, { target: { value: '2026-04-01' } });
    await waitFor(() => expect(getCashBook).toHaveBeenCalledTimes(2));
    expect(screen.getAllByLabelText(/from/i)[0]).toBeTruthy();
    expect(screen.getByText('Opening')).toBeTruthy();
  });

  it('shows the error under the controls and no zero totals when the load fails', async () => {
    getCashBook.mockRejectedValue(new Error('cash down'));
    wrap(<CashBookPage />);
    await screen.findByText(/cash down/);
    expect(screen.getAllByLabelText(/from/i)[0]).toBeTruthy();
    expect(screen.queryByText('Opening')).toBeNull();
  });

  it('hides the Excel export from someone without export rights', async () => {
    getCashBook.mockResolvedValue(CASH);
    wrap(<CashBookPage />);
    await screen.findByText('Opening');
    expect(screen.queryByRole('button', { name: /export/i })).toBeNull();
  });

  it('shows it to someone who can export', async () => {
    auth.canExport = true;
    getCashBook.mockResolvedValue(CASH);
    wrap(<CashBookPage />);
    await screen.findByText('Opening');
    expect(screen.getByRole('button', { name: /export/i })).toBeTruthy();
  });
});

describe('RPT-05 Stock Valuation', () => {
  it('keeps the filters mounted while a new basis loads, and on failure', async () => {
    getStockValuation.mockResolvedValueOnce({ items: [], method: 'WAVG' });
    wrap(<StockValuationPage />);
    const basis = await screen.findByLabelText(/value stock at/i);
    getStockValuation.mockRejectedValue(new Error('valuation down'));
    fireEvent.mouseDown(basis);
    fireEvent.click(await screen.findByText(/purchase price/i));
    await screen.findByText(/valuation down/);
    expect(screen.getByLabelText(/value stock at/i)).toBeTruthy();
  });
});

describe('Cash Book bank filter and row links (RPT-11)', () => {
  it('narrows the book to one bank account and links each row to its document', async () => {
    getCashBook.mockResolvedValue({
      ...CASH,
      rows: [
        { id: 1, date: '2026-10-02', type: 'RECEIPT', number: 'RCT-0007', party: 'Ravi', party_id: 5, mode: 'UPI', inflow: '100', outflow: '0' },
        { id: 2, date: '2026-10-03', type: 'SUPPLIER_PAYMENT', number: 'PAY-0002', party: 'Acme', party_id: 4, mode: 'BANK', inflow: '0', outflow: '40' },
      ],
    });
    wrap(<CashBookPage />);
    const receipt = await screen.findByRole('link', { name: 'RCT-0007' });
    expect(receipt.getAttribute('href')).toBe('/sales/receipts?q=RCT-0007');
    expect(screen.getByRole('link', { name: 'PAY-0002' }).getAttribute('href')).toBe('/purchases/payments?supplier=4');

    fireEvent.mouseDown(screen.getByLabelText(/bank account/i));
    fireEvent.click(await screen.findByText('HDFC Current'));
    await waitFor(() => expect(getCashBook).toHaveBeenLastCalledWith(expect.objectContaining({ bank_account: '3' })));
  });
});
