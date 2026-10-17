import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactElement } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AccountingBankReconPage } from '@/pages/accounting/BankReconWorkspacePage';

const auth = vi.hoisted(() => ({ role: 'OWNER', canPostJournals: true }));
const calls = vi.hoisted(() => ({
  matchManyRecon: vi.fn(async () => ({})),
  finaliseRecon: vi.fn(async () => ({})),
  reopenRecon: vi.fn(async () => ({})),
  unmatchGlRecon: vi.fn(async () => ({})),
  createReconEntry: vi.fn(async () => ({})),
  state: { status: 'IN_PROGRESS', difference: '0.00' },
}));

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ user: { id: 1, role: auth.role, canPostJournals: auth.canPostJournals } }),
}));
vi.mock('@/hooks/useSubscriptionGate', () => ({ useSubscriptionGate: () => ({ writesBlocked: false }) }));

const session = () => ({
  id: 7, account: 1, accountName: 'Bank HDFC', statement: 3, statementName: 'HDFC june', status: calls.state.status,
  statementDate: '2026-06-30', statementClosingBalance: '500.00', difference: calls.state.difference,
  finalisedAt: null, finalisedByName: '', createdAt: '2026-06-30',
  summary: {
    statementDate: '2026-06-30', statementClosingBalance: '500.00', glBalanceAsAt: '500.00', reconciledTotal: '0.00',
    outstandingDeposits: '0.00', outstandingPayments: '0.00', unrecordedBankItems: '0.00', adjustedBankBalance: '500.00',
    adjustedBookBalance: '500.00', difference: calls.state.difference, statementLines: 1, matchedLines: 0, openLines: 1,
  },
});

vi.mock('@/api/resources', () => ({
  listBankReconSessions: async () => ({ results: [session()], count: 1, next: null, previous: null }),
  getBankReconSession: async () => session(),
  listAccounts: async () => [{ id: 9, code: '5200', name: 'Bank Charges', type: 'EXPENSE', isActive: true }],
  listBankStatementsPage: async () => ({ results: [{ id: 3, sourceFilename: 'june.csv' }] }),
  listReconStatementLines: async () => ({
    results: [{ id: 11, txnDate: '2026-06-06', narration: 'NEFT rent', utr: '', amount: '500.00', matchStatus: 'UNMATCHED' }],
    count: 1, next: null, previous: null,
  }),
  listReconLedgerLines: async () => ({
    results: [{ id: 21, entryId: 5, entryNumber: 'JV-5', entryDate: '2026-06-05', narration: 'rent', signedAmount: '500.00' }],
    count: 1, next: null, previous: null,
  }),
  getReconSuggestions: async () => [],
  matchManyRecon: (...a: unknown[]) => calls.matchManyRecon(...(a as [])),
  finaliseRecon: (...a: unknown[]) => calls.finaliseRecon(...(a as [])),
  reopenRecon: (...a: unknown[]) => calls.reopenRecon(...(a as [])),
  unmatchGlRecon: (...a: unknown[]) => calls.unmatchGlRecon(...(a as [])),
  createReconEntry: (...a: unknown[]) => calls.createReconEntry(...(a as [])),
  acceptReconSuggestions: vi.fn(),
  patchBankReconSession: vi.fn(),
  createAccountingBankReconSession: vi.fn(),
  reconReportFile: vi.fn(),
}));

function wrap(ui: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

async function openSession() {
  wrap(<AccountingBankReconPage />);
  await screen.findByText('Bank HDFC');
  await userEvent.click(within(screen.getByRole('table', { name: 'Reconciliations' })).getByRole('button', { name: 'Open' }));
  await screen.findByTestId('recon-summary');
}

describe('Bank reconciliation workspace', () => {
  beforeEach(() => {
    auth.role = 'OWNER';
    auth.canPostJournals = true;
    calls.state.status = 'IN_PROGRESS';
    calls.state.difference = '0.00';
    vi.clearAllMocks();
  });

  it('lists sessions with the bank, status and difference', async () => {
    wrap(<AccountingBankReconPage />);
    expect(await screen.findByText('Bank HDFC')).toBeTruthy();
    expect(screen.getByText('HDFC june')).toBeTruthy();
  });

  it('keeps Match disabled until the selected totals are equal, then matches', async () => {
    await openSession();
    const match = await screen.findByRole('button', { name: 'Match lines' });
    expect((match as HTMLButtonElement).disabled).toBe(true);
    await userEvent.click(await screen.findByRole('checkbox', { name: /Select NEFT rent/ }));
    expect((match as HTMLButtonElement).disabled).toBe(true);
    await userEvent.click(screen.getByRole('checkbox', { name: /Select JV-5/ }));
    await waitFor(() => expect((match as HTMLButtonElement).disabled).toBe(false));
    await userEvent.click(match);
    await waitFor(() => expect(calls.matchManyRecon).toHaveBeenCalledWith(7, { journalLines: [21], bankLines: [11] }));
  });

  it('finalises only through the dialog', async () => {
    await openSession();
    await userEvent.click(screen.getByRole('button', { name: 'Finalise' }));
    expect(calls.finaliseRecon).not.toHaveBeenCalled();
    const buttons = await screen.findAllByRole('button', { name: 'Finalise' });
    await userEvent.click(buttons.at(-1)!);
    await waitFor(() => expect(calls.finaliseRecon).toHaveBeenCalledWith(7, false));
  });

  it('offers a write-off to an owner for a small difference', async () => {
    calls.state.difference = '-5.00';
    await openSession();
    await userEvent.click(screen.getByRole('button', { name: 'Finalise' }));
    const writeOff = await screen.findByRole('button', { name: 'Write off and finalise' });
    await userEvent.click(writeOff);
    await waitFor(() => expect(calls.finaliseRecon).toHaveBeenCalledWith(7, true));
  });

  it('does not offer the write-off to a non-owner', async () => {
    auth.role = 'ACCOUNTANT';
    calls.state.difference = '-5.00';
    await openSession();
    await userEvent.click(screen.getByRole('button', { name: 'Finalise' }));
    expect(screen.queryByRole('button', { name: 'Write off and finalise' })).toBeNull();
    expect(await screen.findByText(/Resolve it before finalising/)).toBeTruthy();
  });

  it('locks every change once finalised and lets only an owner reopen', async () => {
    calls.state.status = 'FINALISED';
    await openSession();
    expect(screen.queryByRole('button', { name: 'Finalise' })).toBeNull();
    expect((screen.getByRole('checkbox', { name: /Select NEFT rent/ }) as HTMLInputElement).disabled).toBe(true);
    expect(screen.getByRole('button', { name: 'Reopen' })).toBeTruthy();
  });

  it('creates an entry from a statement line', async () => {
    await openSession();
    await userEvent.click(await screen.findByRole('button', { name: 'Create entry' }));
    const post = await screen.findByRole('button', { name: 'Post and match' });
    expect((post as HTMLButtonElement).disabled).toBe(true);
  });
});
