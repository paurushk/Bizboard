import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import type { ReactElement } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ExpensesPage } from '@/pages/accounting/ExpensesPage';

const updateExpense = vi.fn(async () => ({ id: 1, notes: 'Updated diesel' }));
const voidExpense = vi.hoisted(() => vi.fn(async () => ({ id: 1, status: 'VOID' })));
const createExpense = vi.hoisted(() => vi.fn(async () => ({ id: 2 })));
const duplicates = vi.hoisted(() => ({ results: [] as Array<{ id: number; number: string }> }));
const settings = vi.hoisted(() => ({ expenseGlStartDate: null as string | null }));
const setMapping = vi.hoisted(() => vi.fn(async () => ({})));
const auth = vi.hoisted(() => ({ role: 'OWNER', canCreatePayments: true }));
const deleteFileAsset = vi.hoisted(() => vi.fn(async () => undefined));
const updateCategory = vi.hoisted(() => vi.fn(async () => ({})));

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 1, email: 'owner@x.test', fullName: 'Owner', role: auth.role, canCreatePayments: auth.canCreatePayments, companyId: 9 },
  }),
}));

vi.mock('@/api/resources', () => ({
  listExpensesRegister: async () => ({
    results: [
      {
        id: 1,
        expenseDate: '2026-09-21',
        number: 'EXP-1',
        partyName: 'HP Pump',
        category: 9,
        categoryName: 'Fuel',
        amount: '500',
        notes: 'Diesel',
        attachment: 55,
        attachmentName: 'bill.pdf',
      },
    ],
    count: 1,
    filteredTotal: '500.00',
  }),
  exportExpenses: vi.fn(async () => new Blob(['x'])),
  downloadFileAsset: vi.fn(async () => new Blob(['x'])),
  deleteFileAsset: (...args: unknown[]) => deleteFileAsset(...(args as [number])),
  listCostCenters: async () => [{ id: 41, code: 'S1', name: 'Shop', isActive: true }],
  updateExpenseCategory: (...args: unknown[]) => updateCategory(...(args as [number, Record<string, unknown>])),
  listRecurringExpenses: async () => [],
  createRecurringExpense: vi.fn(),
  updateRecurringExpense: vi.fn(),
  deleteRecurringExpense: vi.fn(),
  createDueRecurringExpenses: vi.fn(),
  listExpenseCategoriesPage: async () => ({
    results: [{ id: 9, name: 'Fuel', isActive: true, sortOrder: 1 }, { id: 10, name: 'Rent', isActive: true, sortOrder: 2 }],
    count: 1,
    next: null,
    previous: null,
  }),
  createExpense: (...args: unknown[]) => createExpense(...(args as [Record<string, unknown>])),
  findExpenseDuplicates: async () => ({ count: duplicates.results.length, results: duplicates.results }),
  getAccountingSettings: async () => ({ accountingEnabled: true, expenseGlStartDate: settings.expenseGlStartDate }),
  listAccounts: async () => [
    { id: 20, code: '5000', name: 'Expenses', type: 'EXPENSE', isActive: true },
    { id: 21, code: '5810', name: 'Rent expense', type: 'EXPENSE', isActive: true },
    { id: 22, code: '1100', name: 'Cash', type: 'ASSET', isActive: true },
  ],
  listBankAccounts: async () => [{ id: 31, name: 'HDFC Current' }],
  listExpenseCategoryAccounts: async () => [{ id: 1, category: 9, account: 21, accountName: '5810 Rent expense' }],
  setExpenseCategoryAccount: (...args: unknown[]) => setMapping(...(args as [Record<string, unknown>])),
  createExpenseCategory: vi.fn(),
  voidExpense: (...args: unknown[]) => voidExpense(...(args as [number, string])),
  updateExpense: (...args: unknown[]) => updateExpense(...(args as [number, Record<string, unknown>])),
  uploadFile: vi.fn(async () => ({ id: 77 })),
}));

function wrap(ui: ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('ExpensesPage edit', () => {
  it('patches an existing expense from the edit dialog', async () => {
    wrap(<ExpensesPage />);
    await userEvent.click(await screen.findByRole('button', { name: /^edit$/i }));
    const notes = await screen.findByLabelText(/^notes$/i);
    await userEvent.clear(notes);
    await userEvent.type(notes, 'Updated diesel');
    await userEvent.click(screen.getByRole('button', { name: /^save$/i }));
    expect(updateExpense).toHaveBeenCalledWith(
      1,
      expect.objectContaining({ notes: 'Updated diesel', category: 9 }),
    );
  });
});

describe('ExpensesPage void (ACS-14)', () => {
  beforeEach(() => {
    auth.role = 'OWNER';
    auth.canCreatePayments = true;
    voidExpense.mockClear();
    createExpense.mockClear();
    setMapping.mockClear();
    duplicates.results = [];
    settings.expenseGlStartDate = null;
  });

  it('voids with a required reason instead of deleting', async () => {
    wrap(<ExpensesPage />);
    await userEvent.click(await screen.findByRole('button', { name: /^void$/i }));
    const confirm = await screen.findByRole('button', { name: 'Void expense' });
    expect(confirm).toBeDisabled();
    await userEvent.type(screen.getByLabelText(/reason for voiding/i), 'Entered twice');
    await userEvent.click(confirm);
    expect(voidExpense).toHaveBeenCalledWith(1, 'Entered twice');
  });

  it('shows Manage categories to an owner only', async () => {
    wrap(<ExpensesPage />);
    expect(await screen.findByRole('button', { name: /add \/ manage category/i })).toBeTruthy();
  });

  it('hides Manage categories from a non-owner who may still record expenses', async () => {
    auth.role = 'ACCOUNTANT';
    wrap(<ExpensesPage />);
    expect(await screen.findByRole('button', { name: /^edit$/i })).toBeTruthy();
    expect(screen.queryByRole('button', { name: /add \/ manage category/i })).toBeNull();
  });

  it('ACS-16 records how an expense was paid and sends the bank with it', async () => {
    wrap(<ExpensesPage />);
    await userEvent.click(await screen.findByRole('button', { name: /create expense/i }));
    const dialog = await screen.findByRole('dialog');
    await userEvent.click(within(dialog).getByLabelText(/^category$/i));
    await userEvent.click(await screen.findByRole('option', { name: 'Fuel' }));
    await userEvent.type(within(dialog).getByLabelText(/^total$/i), '750');
    await userEvent.click(within(dialog).getByLabelText(/^paid by$/i));
    await userEvent.click(await screen.findByRole('option', { name: 'Bank' }));
    const save = within(dialog).getByRole('button', { name: /^save$/i });
    expect(save).toBeDisabled(); // a bank expense needs its bank account
    await userEvent.click(within(dialog).getByLabelText(/^bank account/i));
    await userEvent.click(await screen.findByRole('option', { name: 'HDFC Current' }));
    expect(save).toBeEnabled();
    await userEvent.click(save);
    expect(createExpense).toHaveBeenCalledWith(
      expect.objectContaining({ category: 9, amount: 750, paymentMode: 'BANK', bankAccount: 31, expenseAccount: null }),
    );
  });

  it('ACS-16 shows the ledger an expense will post to and lets the user override it', async () => {
    wrap(<ExpensesPage />);
    await userEvent.click(await screen.findByRole('button', { name: /create expense/i }));
    const dialog = await screen.findByRole('dialog');
    await userEvent.click(within(dialog).getByLabelText(/^category$/i));
    await userEvent.click(await screen.findByRole('option', { name: 'Fuel' }));
    expect(await within(dialog).findByText(/Leave blank to post to 5810 Rent expense/)).toBeTruthy();
    await userEvent.type(within(dialog).getByLabelText(/^expense ledger$/i), 'expenses');
    expect(screen.queryByRole('option', { name: /1100/ })).toBeNull(); // only expense accounts are offered
    await userEvent.click(await screen.findByRole('option', { name: /5000 — Expenses/ }));
    await userEvent.type(within(dialog).getByLabelText(/^total$/i), '10');
    await userEvent.click(within(dialog).getByRole('button', { name: /^save$/i }));
    expect(createExpense).toHaveBeenCalledWith(expect.objectContaining({ expenseAccount: 20, paymentMode: 'CASH', bankAccount: null }));
  });

  it('ACS-16 warns about a likely duplicate once, then saves on the second click', async () => {
    duplicates.results = [{ id: 7, number: 'EXP-7' }];
    wrap(<ExpensesPage />);
    await userEvent.click(await screen.findByRole('button', { name: /create expense/i }));
    const dialog = await screen.findByRole('dialog');
    await userEvent.click(within(dialog).getByLabelText(/^category$/i));
    await userEvent.click(await screen.findByRole('option', { name: 'Fuel' }));
    await userEvent.type(within(dialog).getByLabelText(/^total$/i), '500');
    await userEvent.click(within(dialog).getByRole('button', { name: /^save$/i }));
    expect(await within(dialog).findByText(/duplicate of EXP-7/)).toBeTruthy();
    expect(createExpense).not.toHaveBeenCalled();
    await userEvent.click(within(dialog).getByRole('button', { name: /save anyway/i }));
    expect(createExpense).toHaveBeenCalledOnce();
  });

  it('ACS-15 shows an In books column once posting is on', async () => {
    settings.expenseGlStartDate = '2026-10-01';
    wrap(<ExpensesPage />);
    expect(await screen.findByText('Not posted')).toBeTruthy();
  });

  it('ACS-15 lets the owner map a category to an expense ledger', async () => {
    wrap(<ExpensesPage />);
    await userEvent.click(await screen.findByRole('button', { name: /add \/ manage category/i }));
    const dialog = await screen.findByRole('dialog');
    const picker = (await within(dialog).findAllByLabelText(/^posts to$/i))[0];
    await userEvent.click(picker);
    await userEvent.click(await screen.findByRole('option', { name: /5000 — Expenses/ }));
    expect(setMapping).toHaveBeenCalledWith({ category: 9, account: 20 });
  });
});

describe('ExpensesPage register and extras (ACS-17)', () => {
  beforeEach(() => {
    auth.role = 'OWNER';
    auth.canCreatePayments = true;
    createExpense.mockClear();
    updateCategory.mockClear();
    deleteFileAsset.mockClear();
    duplicates.results = [];
    settings.expenseGlStartDate = null;
  });

  it('shows how many expenses match and the filtered total', async () => {
    wrap(<ExpensesPage />);
    expect((await screen.findByTestId('expense-register-total')).textContent).toMatch(/1 expense\(s\) match\. Total .*500/);
    expect(screen.getByRole('button', { name: 'bill.pdf' })).toBeTruthy();
  });

  it('sends GST, ITC, TDS and the cost centre with the expense', async () => {
    wrap(<ExpensesPage />);
    await userEvent.click(await screen.findByRole('button', { name: /create expense/i }));
    const dialog = await screen.findByRole('dialog');
    await userEvent.click(within(dialog).getByLabelText(/^category$/i));
    await userEvent.click(await screen.findByRole('option', { name: 'Fuel' }));
    await userEvent.type(within(dialog).getByLabelText(/^total$/i), '1180');
    await userEvent.click(within(dialog).getByLabelText(/^cost centre$/i));
    await userEvent.click(await screen.findByRole('option', { name: /S1 · Shop/ }));
    await userEvent.click(within(dialog).getByText('GST and TDS (optional)'));
    await userEvent.click(within(dialog).getByLabelText(/^GST on this bill$/i));
    await userEvent.click(await screen.findByRole('option', { name: /Same state/ }));
    await userEvent.type(within(dialog).getByLabelText(/^CGST amount$/i), '90');
    await userEvent.type(within(dialog).getByLabelText(/^Supplier GSTIN$/i), '27aapfu0939f1zv');
    await userEvent.click(within(dialog).getByLabelText(/Claim input tax credit/));
    await userEvent.type(within(dialog).getByLabelText(/^TDS section$/i), '194c');
    await userEvent.type(within(dialog).getByLabelText(/^TDS deducted$/i), '100');
    await userEvent.click(within(dialog).getByRole('button', { name: /^save$/i }));
    expect(createExpense).toHaveBeenCalledWith(
      expect.objectContaining({
        costCenter: 41, cgstAmount: 90, sgstAmount: 90, igstAmount: 0, itcEligible: true,
        supplierGstin: '27AAPFU0939F1ZV', tdsSection: '194C', tdsAmount: 100,
      }),
    );
  });

  it('blocks saving when ITC is claimed without a GSTIN', async () => {
    wrap(<ExpensesPage />);
    await userEvent.click(await screen.findByRole('button', { name: /create expense/i }));
    const dialog = await screen.findByRole('dialog');
    await userEvent.click(within(dialog).getByLabelText(/^category$/i));
    await userEvent.click(await screen.findByRole('option', { name: 'Fuel' }));
    await userEvent.type(within(dialog).getByLabelText(/^total$/i), '118');
    await userEvent.click(within(dialog).getByText('GST and TDS (optional)'));
    await userEvent.click(within(dialog).getByLabelText(/^GST on this bill$/i));
    await userEvent.click(await screen.findByRole('option', { name: /Other state/ }));
    await userEvent.type(within(dialog).getByLabelText(/^IGST amount$/i), '18');
    await userEvent.click(within(dialog).getByLabelText(/Claim input tax credit/));
    expect(within(dialog).getByText('Input tax credit needs the supplier GSTIN.')).toBeTruthy();
    expect(within(dialog).getByRole('button', { name: /^save$/i })).toBeDisabled();
  });

  it('removes an uploaded file again when the dialog is cancelled without saving', async () => {
    wrap(<ExpensesPage />);
    await userEvent.click(await screen.findByRole('button', { name: /create expense/i }));
    const dialog = await screen.findByRole('dialog');
    const input = dialog.querySelector('input[type="file"]') as HTMLInputElement;
    await userEvent.upload(input, new File(['x'], 'bill.png', { type: 'image/png' }));
    await within(dialog).findByText(/#77/);
    await userEvent.click(within(dialog).getByRole('button', { name: /^cancel$/i }));
    expect(deleteFileAsset).toHaveBeenCalledWith(77);
  });

  it('lets an owner rename and reorder categories', async () => {
    wrap(<ExpensesPage />);
    await userEvent.click(await screen.findByRole('button', { name: /add \/ manage category/i }));
    const dialog = await screen.findByRole('dialog');
    const name = await within(dialog).findByLabelText('Category name Fuel');
    await userEvent.clear(name);
    await userEvent.type(name, 'Diesel');
    await userEvent.click(within(dialog).getAllByRole('button', { name: /^save$/i })[0]);
    expect(updateCategory).toHaveBeenCalledWith(9, { name: 'Diesel' });
    updateCategory.mockClear();
    await userEvent.click(within(dialog).getByRole('button', { name: 'Move down Fuel' }));
    expect(updateCategory).toHaveBeenCalledWith(10, { sortOrder: 1 });
    expect(updateCategory).toHaveBeenCalledWith(9, { sortOrder: 2 });
  });

  it('opens the recurring expenses dialog', async () => {
    wrap(<ExpensesPage />);
    await userEvent.click(await screen.findByRole('button', { name: 'Recurring expenses' }));
    expect(await screen.findByText('No recurring expenses yet.')).toBeTruthy();
  });
});
