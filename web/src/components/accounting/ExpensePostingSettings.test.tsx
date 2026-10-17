import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactElement } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ExpensePostingSettings } from '@/components/accounting/ExpensePostingSettings';

const state = vi.hoisted(() => ({
  settings: { accountingEnabled: true, expenseGlStartDate: null as string | null, expenseGlPending: { count: 0, total: '0' } },
  update: vi.fn(async () => ({})),
  post: vi.fn(async (dryRun: boolean) => ({ posted: 3, total: '3000', skipped: [], dryRun })),
}));

vi.mock('@/components/billing', () => ({ todayIso: () => '2026-10-17' }));
vi.mock('@/api/resources', () => ({
  getAccountingSettings: async () => state.settings,
  updateAccountingSettings: (...args: unknown[]) => state.update(...(args as [])),
  postPendingExpenses: (dryRun: boolean) => state.post(dryRun),
}));

function wrap(ui: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe('ExpensePostingSettings (ACS-15)', () => {
  beforeEach(() => {
    state.settings = { accountingEnabled: true, expenseGlStartDate: null, expenseGlPending: { count: 0, total: '0' } };
    state.update.mockClear();
    state.post.mockClear();
  });

  it('says expenses are not posted and starts posting from the chosen date', async () => {
    wrap(<ExpensePostingSettings />);
    expect(await screen.findByText('Expenses are not posted to the books.')).toBeTruthy();
    const start = screen.getByRole('button', { name: 'Start posting' });
    expect(start).toBeDisabled();
    await userEvent.type(screen.getByLabelText('Post expenses from'), '2026-10-01');
    await userEvent.click(start);
    expect(state.update).toHaveBeenCalledWith({ expenseGlStartDate: '2026-10-01' });
  });

  it('shows what is waiting, previews it, then posts it', async () => {
    state.settings = {
      accountingEnabled: true, expenseGlStartDate: '2026-10-01', expenseGlPending: { count: 3, total: '3000' },
    };
    wrap(<ExpensePostingSettings />);
    expect(await screen.findByText(/3 expense\(s\), .*3,000.*waiting to be posted/)).toBeTruthy();
    await userEvent.click(screen.getByRole('button', { name: 'Preview' }));
    expect(await screen.findByText(/Would post 3 expense\(s\)/)).toBeTruthy();
    expect(state.post).toHaveBeenLastCalledWith(true);
    await userEvent.click(screen.getByRole('button', { name: 'Post them now' }));
    expect(state.post).toHaveBeenLastCalledWith(false);
    expect(await screen.findByText(/Posted 3 expense\(s\)/)).toBeTruthy();
  });

  it('can switch posting off', async () => {
    state.settings = { accountingEnabled: true, expenseGlStartDate: '2026-10-01', expenseGlPending: { count: 0, total: '0' } };
    wrap(<ExpensePostingSettings />);
    await userEvent.click(await screen.findByRole('button', { name: 'Stop posting' }));
    expect(state.update).toHaveBeenCalledWith({ expenseGlStartDate: null });
  });

  it('renders nothing while accounting is off', async () => {
    state.settings = { accountingEnabled: false, expenseGlStartDate: null, expenseGlPending: { count: 0, total: '0' } };
    const { container } = wrap(<ExpensePostingSettings />);
    await new Promise((r) => setTimeout(r, 50));
    expect(container.querySelector('[data-testid="expense-posting-settings"]')).toBeNull();
  });
});
