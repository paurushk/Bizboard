import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { BalanceSheetPage, TrialBalancePage } from '@/pages/phase/AccountingReportsPages';

const { getReport, books, auth } = vi.hoisted(() => ({
  getReport: vi.fn(),
  books: { trusted: true },
  auth: { canExport: true },
}));

vi.mock('@/api/resources', async () => {
  const actual = await vi.importActual<typeof import('@/api/resources')>('@/api/resources');
  return {
    ...actual,
    getAccountingReport: (...a: unknown[]) => getReport(...a),
    downloadAccountingReport: vi.fn(),
    listCostCenters: async () => [],
  };
});
vi.mock('@/components/AccountingBackfillBanner', () => ({
  AccountingBackfillBanner: () => null,
  useBooksState: () => ({ state: books.trusted ? 'ok' : 'backfill', trusted: books.trusted }),
}));
vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 1, email: 'a@x.test', fullName: 'A', role: 'ACCOUNTANT', canExport: auth.canExport, companyId: 9 },
  }),
}));

function wrap(node: JSX.Element) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{node}</MemoryRouter>
    </QueryClientProvider>,
  );
}

const sheet = (equationHolds: boolean, asOfDefaulted = false) => ({
  asOf: '2026-10-18',
  asOfDefaulted,
  equationHolds,
  scheduleIii: {
    sections: [
      { key: 'current_assets', label: 'Current assets', amount: '5000.00', lines: [{ key: 'cash', label: 'Cash and cash equivalents', amount: '5000.00', accounts: [] }] },
      { key: 'equity', label: 'Equity', amount: '3000.00', lines: [{ key: 'surplus', label: 'Surplus in statement of profit and loss', amount: '3000.00', accounts: [] }] },
      { key: 'current_liabilities', label: 'Current liabilities', amount: '2000.00', lines: [{ key: 'tp', label: 'Trade payables', amount: '2000.00', accounts: [] }] },
    ],
  },
});

beforeEach(() => {
  vi.clearAllMocks();
  books.trusted = true;
  auth.canExport = true;
});

describe('Balance Sheet', () => {
  it('shows assets, equity and liabilities with totals and a balanced check', async () => {
    getReport.mockResolvedValue(sheet(true));
    wrap(<BalanceSheetPage />);
    await screen.findByText('Cash and cash equivalents');
    expect(screen.getByText('Total assets')).toBeTruthy();
    expect(screen.getByText('Total equity and liabilities')).toBeTruthy();
    expect(screen.getByText(/Balanced/)).toBeTruthy();
  });

  it('warns with the gap when the books do not balance', async () => {
    getReport.mockResolvedValue(sheet(false));
    wrap(<BalanceSheetPage />);
    await screen.findByText(/Not balanced/);
  });

  it('never reads a missing balance flag as balanced', async () => {
    getReport.mockResolvedValue({ ...sheet(true), equationHolds: undefined });
    wrap(<BalanceSheetPage />);
    await screen.findByText(/Not balanced/);
  });

  it('says when the date was filled in by the server', async () => {
    getReport.mockResolvedValue(sheet(true, true));
    wrap(<BalanceSheetPage />);
    await screen.findByText(/end of the financial year/);
  });

  it('hides every amount until the books are trusted', async () => {
    books.trusted = false;
    getReport.mockResolvedValue(sheet(true));
    wrap(<BalanceSheetPage />);
    await screen.findByText('Cash and cash equivalents');
    expect(document.body.textContent).not.toMatch(/5,000/);
  });

  it('keeps the date box and shows the error when the load fails', async () => {
    getReport.mockRejectedValue(new Error('bs down'));
    wrap(<BalanceSheetPage />);
    await screen.findByText(/bs down/);
    expect(screen.getByLabelText('As of')).toBeTruthy();
  });

  it('hides Download from someone without export rights', async () => {
    auth.canExport = false;
    getReport.mockResolvedValue(sheet(true));
    wrap(<BalanceSheetPage />);
    await screen.findByText('Cash and cash equivalents');
    expect(screen.queryByRole('button', { name: /download/i })).toBeNull();
  });
});

describe('Trial Balance', () => {
  const tb = {
    totalDebit: '100.00',
    totalCredit: '100.00',
    balanced: true,
    rows: [{ accountId: 5, accountCode: '1100', accountName: 'Cash', accountType: 'ASSET', debit: '100.00', credit: '0.00', balance: '100.00' }],
  };

  it('ends with a totals row', async () => {
    getReport.mockResolvedValue(tb);
    wrap(<TrialBalancePage />);
    await screen.findByText('Cash');
    await waitFor(() => expect(screen.getByText('Total')).toBeTruthy());
  });

  it('masks table amounts like the banner when books are untrusted', async () => {
    books.trusted = false;
    getReport.mockResolvedValue(tb);
    wrap(<TrialBalancePage />);
    await screen.findByText('Cash');
    expect(document.body.textContent).not.toMatch(/100\.00/);
  });

  it('lists the activities that are not in these books yet (WP-F3)', async () => {
    getReport.mockResolvedValue({
      ...tb,
      ledgerGaps: [
        { flag: 'ENABLE_FIXED_ASSETS', covers: ['Fixed asset'], note: 'server note' },
        { flag: 'SOME_NEW_FLAG', covers: ['New thing'], note: 'Server explains the new gap' },
      ],
    });
    wrap(<TrialBalancePage />);
    await screen.findByText('Cash');
    expect(screen.getByText('Not in these books yet')).toBeTruthy();
    expect(screen.getByText(/Fixed assets and depreciation/)).toBeTruthy();
    expect(screen.getByText('Server explains the new gap')).toBeTruthy();
  });

  it('shows no gap note when every posting is on', async () => {
    getReport.mockResolvedValue({ ...tb, ledgerGaps: [] });
    wrap(<TrialBalancePage />);
    await screen.findByText('Cash');
    expect(screen.queryByTestId('ledger-gaps')).toBeNull();
  });

  it('opens the ledger lines behind an account from its code', async () => {
    getReport.mockResolvedValue(tb);
    wrap(<TrialBalancePage />);
    const link = await screen.findByRole('link', { name: '1100' });
    expect(link.getAttribute('href')).toMatch(/^\/reports\/day-book\?account=5&from=\d{4}-\d{2}-\d{2}&to=\d{4}-\d{2}-\d{2}$/);
  });
});
