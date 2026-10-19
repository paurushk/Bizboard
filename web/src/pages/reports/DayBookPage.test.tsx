import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import type { ReactElement } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { DayBookPage } from '@/pages/reports/DayBookPage';

const state = vi.hoisted(() => ({ ties: true, balanced: true, ledgerCalls: [] as unknown[] }));

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ user: { id: 1, email: 'o@x.test', fullName: 'O', role: 'OWNER', canExport: true, companyId: 9 } }),
}));

vi.mock('@/components/billing', () => ({ todayIso: () => '2026-09-21' }));
vi.mock('@/api/resources', () => ({
  getDayBook: async () => ({
    date: '2026-09-21',
    inflow: '200',
    outflow: '50',
    net: '150',
    adjustments: { salesReturns: '30', creditNotes: '0', debitNotes: '0' },
    disclaimer: 'Cheque receipts count only when CLEARED. This is not a Cash Book relabel.',
    rows: [{ id: 1, date: '2026-09-21', txnType: 'PAYMENT_IN', number: 'RCT-1', party: 'Ravi', amount: '200', status: 'POSTED' }],
  }),
  getLedgerDayBook: async (p: unknown) => {
    state.ledgerCalls.push(p);
    return {
      dateFrom: '2026-09-21', dateTo: '2026-09-21', count: 2,
      results: [
        { id: 1, date: '2026-09-21', voucher: 'JV-1', entryId: 1, voucherType: 'SALES', voucherTypeLabel: 'Sales', accountCode: '1100', accountName: 'Cash', party: '', costCenter: '', debit: '500.00', credit: '0.00', narration: 'cake', status: 'POSTED', sourceLabel: 'a sales invoice', sourcePath: '/sales/history/1' },
        { id: 2, date: '2026-09-21', voucher: 'JV-1', entryId: 1, voucherType: 'SALES', voucherTypeLabel: 'Sales', accountCode: '4100', accountName: 'Sales', party: 'Ravi', costCenter: '', debit: '0.00', credit: '500.00', narration: 'cake', status: 'POSTED', sourceLabel: 'a sales invoice', sourcePath: '/sales/history/1' },
      ],
      totals: { debit: '500.00', credit: '500.00', balanced: state.balanced },
      dayTotals: [{ date: '2026-09-21', debit: '500.00', credit: '500.00', balanced: state.balanced }],
      voucherTypes: [{ key: 'SALES', label: 'Sales' }],
      tieOut: { trialBalanceDebit: '500.00', trialBalanceCredit: '500.00', ties: state.ties },
      previous: '2026-09-20', next: '2026-09-22',
    };
  },
  exportLedgerDayBook: vi.fn(async () => new Blob(['x'])),
  listAccounts: async () => [{ id: 3, code: '1100', name: 'Cash', type: 'ASSET', isActive: true }],
}));

function wrap(ui: ReactElement, path = '/reports/day-book') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('DayBookPage', () => {
  beforeEach(() => {
    state.ties = true;
    state.balanced = true;
    state.ledgerCalls = [];
  });

  it('lists every ledger line with its totals and says they tie to the trial balance', async () => {
    wrap(<DayBookPage />);
    expect(await screen.findAllByText('JV-1')).toHaveLength(2);
    expect(screen.getByText('1100 Cash')).toBeTruthy();
    expect(screen.getByTestId('day-book-tie-out').textContent).toMatch(/match the trial balance/);
    expect(screen.getByTestId('day-book-totals').textContent).toMatch(/Balanced/);
  });

  it('warns loudly when the totals do not tie or a day does not balance', async () => {
    state.ties = false;
    state.balanced = false;
    wrap(<DayBookPage />);
    expect((await screen.findByTestId('day-book-tie-out')).textContent).toMatch(/do not match the trial balance/);
    expect(screen.getByText(/Debits and credits do not match on: 2026-09-21/)).toBeTruthy();
  });

  it('moves to the next day and asks the server for it', async () => {
    wrap(<DayBookPage />);
    await screen.findAllByText('JV-1');
    await userEvent.click(screen.getByRole('button', { name: 'Next day' }));
    await waitFor(() => expect((state.ledgerCalls.at(-1) as Record<string, string>).date_from).toBe('2026-09-22'));
  });

  it('opens on the account named in the link', async () => {
    wrap(<DayBookPage />, '/reports/day-book?account=3');
    await screen.findAllByText('JV-1');
    expect((state.ledgerCalls.at(-1) as Record<string, string>).account).toBe('3');
  });

  it('keeps the cash view as its own tab with returns shown apart from cash', async () => {
    wrap(<DayBookPage />);
    await userEvent.click(await screen.findByRole('tab', { name: 'Daily cash summary' }));
    expect(await screen.findByText(/cheque receipts count only when cleared/i)).toBeTruthy();
    expect(screen.getByText('Inflow')).toBeTruthy();
    expect(screen.getByText('RCT-1')).toBeTruthy();
    expect(screen.getByText(/Sales returns .*30/)).toBeTruthy();
  });
});
