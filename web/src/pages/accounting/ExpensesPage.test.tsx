import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import type { ReactElement } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { ExpensesPage } from '@/pages/accounting/ExpensesPage';

const updateExpense = vi.fn(async () => ({ id: 1, notes: 'Updated diesel' }));

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 1, email: 'owner@x.test', fullName: 'Owner', role: 'OWNER', companyId: 9 },
  }),
}));

vi.mock('@/api/resources', () => ({
  listExpensesPage: async () => ({
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
      },
    ],
    count: 1,
    next: null,
    previous: null,
  }),
  listExpenseCategoriesPage: async () => ({
    results: [{ id: 9, name: 'Fuel' }],
    count: 1,
    next: null,
    previous: null,
  }),
  createExpense: vi.fn(),
  createExpenseCategory: vi.fn(),
  deleteExpense: vi.fn(),
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
