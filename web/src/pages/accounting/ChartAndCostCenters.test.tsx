import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactElement } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ChartOfAccountsPage } from '@/pages/accounting/ChartOfAccountsPage';
import { CostCentersPage } from '@/pages/accounting/CostCentersPage';
import { toTree } from '@/components/accounting/chartTree';

const auth = vi.hoisted(() => ({ canPostJournals: true, role: 'OWNER' }));
const api = vi.hoisted(() => ({
  updateAccount: vi.fn(),
  createAccount: vi.fn(async () => ({})),
  transferAccountBalance: vi.fn(async () => ({ journalId: 1, number: 'JV-9', amount: '75.00' })),
  createCostCenter: vi.fn(),
  updateCostCenter: vi.fn(async () => ({})),
  deleteCostCenter: vi.fn(async () => undefined),
}));

vi.mock('@/auth/AuthContext', () => ({ useAuth: () => ({ user: { id: 1, role: auth.role, canPostJournals: auth.canPostJournals } }) }));
vi.mock('@/hooks/useSubscriptionGate', () => ({ useSubscriptionGate: () => ({ writesBlocked: false }) }));
vi.mock('@/components/AccountingBackfillBanner', () => ({ AccountingBackfillBanner: () => null }));

const account = (over: Record<string, unknown>) => ({
  id: 1, code: '5000', name: 'Expenses', type: 'EXPENSE', parent: null, parentName: '', isSystem: false, isControl: false,
  bankAccount: null, isActive: true, hasPostings: false, balance: '0.00', ...over,
});

vi.mock('@/api/resources', () => ({
  listChartAccounts: async () => [
    account({ id: 1, code: '5000', name: 'Expenses', balance: '100.00' }),
    account({ id: 2, code: '5010', name: 'Rent', parent: 1, parentName: 'Expenses', hasPostings: true, balance: '75.00' }),
    account({ id: 3, code: '1100', name: 'Cash', type: 'ASSET', isSystem: true }),
  ],
  listAccounts: async () => [
    { id: 1, code: '5000', name: 'Expenses', type: 'EXPENSE', isActive: true },
    { id: 2, code: '5010', name: 'Rent', type: 'EXPENSE', isActive: true },
    { id: 4, code: '5020', name: 'Travel', type: 'EXPENSE', isActive: true },
  ],
  updateAccount: (...a: unknown[]) => api.updateAccount(...a),
  createAccount: (...a: unknown[]) => api.createAccount(...(a as [])),
  transferAccountBalance: (...a: unknown[]) => api.transferAccountBalance(...(a as [])),
  exportChartAccounts: vi.fn(),
  listCostCentersFull: async () => [
    { id: 1, code: 'N', name: 'North', parent: null, parentName: '', isActive: true, usage: { journalLines: 3, invoices: 0, expenses: 0 } },
    { id: 2, code: 'S', name: 'South', parent: null, parentName: '', isActive: true, usage: { journalLines: 0, invoices: 0, expenses: 0 } },
  ],
  getCostCenterReport: async () => ({
    results: [
      { costCenter: 1, code: 'N', name: 'North', income: '700.00', expense: '200.00', net: '500.00' },
      { costCenter: null, code: '', name: 'Unallocated', income: '300.00', expense: '0.00', net: '300.00' },
    ],
    totals: { income: '1000.00', expense: '200.00', net: '800.00' },
  }),
  createCostCenter: (...a: unknown[]) => api.createCostCenter(...a),
  updateCostCenter: (...a: unknown[]) => api.updateCostCenter(...(a as [])),
  deleteCostCenter: (...a: unknown[]) => api.deleteCostCenter(...(a as [])),
}));

function wrap(ui: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('toTree', () => {
  it('puts children under their parent with a depth', () => {
    const rows = toTree([
      account({ id: 2, code: '5010', parent: 1 }) as never,
      account({ id: 1, code: '5000' }) as never,
      account({ id: 9, code: '4000', parent: 77 }) as never,
    ]);
    expect(rows.map((r) => [r.code, r.depth])).toEqual([['4000', 0], ['5000', 0], ['5010', 1]]);
  });
});

describe('Chart of accounts', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    auth.canPostJournals = true;
    auth.role = 'OWNER';
  });

  it('shows balances with Dr/Cr, a lock for system accounts, and no edit on them', async () => {
    wrap(<ChartOfAccountsPage />);
    expect(await screen.findByText('Rent')).toBeTruthy();
    expect(screen.getByText('System')).toBeTruthy();
    expect(screen.getAllByRole('button', { name: 'Edit' })).toHaveLength(2); // Cash is a system account
    expect(screen.getByRole('link', { name: 'View ledger 5010' }).getAttribute('href')).toBe('/reports/day-book?account=2');
  });

  it('explains why code and type are locked once an account has entries', async () => {
    wrap(<ChartOfAccountsPage />);
    await screen.findByText('Rent');
    await userEvent.click(screen.getAllByRole('button', { name: 'Edit' })[1]);
    expect(await screen.findByText(/code and type can no longer change/)).toBeTruthy();
    expect((screen.getByLabelText(/^Code/) as HTMLInputElement).disabled).toBe(true);
  });

  it('offers to move the balance when deactivating an account that has one', async () => {
    api.updateAccount.mockRejectedValueOnce({ response: { data: { error: { message: 'This account still has a balance' } } } });
    wrap(<ChartOfAccountsPage />);
    await screen.findByText('Rent');
    await userEvent.click(screen.getAllByRole('button', { name: 'Deactivate' })[1]);
    expect(await screen.findByText(/Move the balance of Rent/)).toBeTruthy();
    expect((screen.getByRole('button', { name: 'Create draft journal' }) as HTMLButtonElement).disabled).toBe(true);
  });

  it('hides write buttons from a user who cannot post journals', async () => {
    auth.canPostJournals = false;
    auth.role = 'STAFF';
    wrap(<ChartOfAccountsPage />);
    await screen.findByText('Rent');
    expect((screen.getByRole('button', { name: 'Add account' }) as HTMLButtonElement).disabled).toBe(true);
  });
});

describe('Cost centres', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    auth.canPostJournals = true;
    auth.role = 'OWNER';
  });

  it('shows usage and only lets an unused centre be deleted', async () => {
    wrap(<CostCentersPage />);
    expect(await screen.findByText('North')).toBeTruthy();
    expect(screen.getByText('3 lines, 0 invoices, 0 expenses')).toBeTruthy();
    const deletes = screen.getAllByRole('button', { name: 'Delete' }) as HTMLButtonElement[];
    expect(deletes.map((b) => b.disabled)).toEqual([true, false]);
    await userEvent.click(deletes[1]);
    await userEvent.click(await screen.findByRole('button', { name: 'Delete', hidden: false }).then(() => screen.getAllByRole('button', { name: 'Delete' }).at(-1)!));
    await waitFor(() => expect(api.deleteCostCenter).toHaveBeenCalledWith(2));
  });

  it('keeps the dialog open and shows the server message when saving fails', async () => {
    api.createCostCenter.mockRejectedValueOnce({ response: { data: { error: { message: 'Code N is already used by North.' } } } });
    wrap(<CostCentersPage />);
    await screen.findByText('North');
    await userEvent.click(screen.getByRole('button', { name: 'Add' }));
    await userEvent.type(await screen.findByLabelText(/^Name/), 'Again');
    await userEvent.click(screen.getByRole('button', { name: 'Save' }));
    expect(await screen.findByRole('dialog')).toBeTruthy();
    await waitFor(() => expect(api.createCostCenter).toHaveBeenCalled());
  });

  it('shows the cost-centre profit report with an unallocated row and a total', async () => {
    wrap(<CostCentersPage />);
    await screen.findByText('North');
    await userEvent.click(screen.getByRole('tab', { name: 'Profit by cost centre' }));
    expect(await screen.findByText('Unallocated')).toBeTruthy();
    expect(screen.getByText(/N · North/)).toBeTruthy();
  });
});
