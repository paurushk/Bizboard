import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import type { ReactElement } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { PeriodsPage } from '@/pages/phase/PeriodsPage';
import * as resources from '@/api/resources';

const auth = vi.hoisted(() => ({ role: 'OWNER' }));

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ user: { id: 1, role: auth.role, canViewFinancialReports: true } }),
}));

vi.mock('@/hooks/useSubscriptionGate', () => ({
  useSubscriptionGate: () => ({ writesBlocked: false }),
}));

vi.mock('@/config/features', () => ({
  isGstrReportsEnabled: () => false,
}));

const summary = vi.hoisted(() => ({
  rows: [] as Array<Record<string, unknown>>,
}));

vi.mock('@/api/resources', () => ({
  getCloseSummary: async () => summary.rows,
  getCloseReadiness: vi.fn(async () => ({
    period: 2,
    name: 'Oct',
    status: 'OPEN',
    gstStatus: 'OPEN',
    earlierOpenPeriod: null,
    blockers: [{ code: 'EXPENSE_MISSING_POSTING', severity: 'error', message: 'Expenses are not posted.', title: 't', fixPath: '/accounting/expenses' }],
    advisory: [],
    canSoftClose: false,
    canClose: false,
    canReopen: false,
  })),
  createAccountingPeriod: vi.fn(),
  closeAccountingAndGstPeriod: vi.fn(),
  softCloseAccountingPeriod: vi.fn(),
  reopenAccountingPeriod: vi.fn(async () => ({})),
  generateAccountingYear: vi.fn(async () => ({ created: ['Apr'], skipped: [] })),
  previewFinancialYearClose: vi.fn(async () => ({
    fyStart: '2026-04-01', fyEnd: '2027-03-31', income: '1000.00', expense: '400.00', netProfit: '600.00',
    movesToAccount: '3100 Retained Earnings', draftInvoices: 0, periods: [{ id: 1, name: 'Apr', status: 'OPEN' }],
    blockers: [], canClose: true, alreadyClosed: false, journalId: null,
  })),
  closeFinancialYear: vi.fn(),
  reverseFinancialYearClose: vi.fn(),
}));

vi.mock('@/api/client', () => ({
  apiClient: { get: async () => ({ data: [] }) },
  unwrapData: (data: unknown) => data,
  getErrorMessage: () => 'error',
}));

function wrap(ui: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

const sep = { id: 1, name: 'Sep', startDate: '2026-09-01', endDate: '2026-09-30', status: 'CLOSED', gstStatus: 'CLOSED', blockerCount: null, blockedByEarlier: false };
const oct = { id: 2, name: 'Oct', startDate: '2026-10-01', endDate: '2026-10-31', status: 'OPEN', gstStatus: 'OPEN', blockerCount: 0, blockedByEarlier: false };
const nov = { id: 3, name: 'Nov', startDate: '2026-11-01', endDate: '2026-11-30', status: 'OPEN', gstStatus: 'OPEN', blockerCount: null, blockedByEarlier: true };

describe('PeriodsPage close control', () => {
  beforeEach(() => {
    auth.role = 'OWNER';
    summary.rows = [nov, oct, sep];
    vi.mocked(resources.closeAccountingAndGstPeriod).mockClear();
  });

  it('shows books and GST status per month and explains why a later month waits', async () => {
    wrap(<PeriodsPage />);
    expect(await screen.findByText('Oct')).toBeTruthy();
    expect(screen.getByText('Waiting for earlier month')).toBeTruthy();
    expect(screen.getByText('Close Oct first')).toBeTruthy();
    // Nov's close buttons are disabled; Oct's are not.
    const closeButtons = screen.getAllByRole('button', { name: 'Close period' }) as HTMLButtonElement[];
    expect(closeButtons.map((b) => b.disabled)).toEqual([true, false]);
  });

  it('lets an owner close the month through the in-app dialog, never window.confirm', async () => {
    const nativeConfirm = vi.spyOn(window, 'confirm');
    wrap(<PeriodsPage />);
    await screen.findByText('Oct');
    await userEvent.click(screen.getAllByRole('button', { name: 'Close period' })[1]);
    expect(resources.closeAccountingAndGstPeriod).not.toHaveBeenCalled();
    const dialog = await screen.findByRole('dialog');
    expect(dialog.textContent).toMatch(/Close books and GST\?/);
    await userEvent.click(screen.getAllByRole('button', { name: 'Close period' }).at(-1)!);
    expect(resources.closeAccountingAndGstPeriod).toHaveBeenCalledWith(2);
    expect(nativeConfirm).not.toHaveBeenCalled();
    nativeConfirm.mockRestore();
  });

  it('cancelling the dialog closes nothing', async () => {
    wrap(<PeriodsPage />);
    await screen.findByText('Oct');
    await userEvent.click(screen.getAllByRole('button', { name: 'Close period' })[1]);
    await userEvent.click(await screen.findByRole('button', { name: 'Cancel' }));
    expect(resources.closeAccountingAndGstPeriod).not.toHaveBeenCalled();
  });

  it('expands a month with blockers and links to the fix', async () => {
    summary.rows = [{ ...oct, blockerCount: 1 }, sep];
    wrap(<PeriodsPage />);
    await userEvent.click(await screen.findByRole('button', { name: '1 blocker(s)' }));
    expect(await screen.findByText('Expenses are not posted.')).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Fix' }).getAttribute('href')).toBe('/accounting/expenses');
  });

  it('asks for a reason before reopening the latest closed month', async () => {
    summary.rows = [oct, sep];
    wrap(<PeriodsPage />);
    await screen.findByText('Oct');
    // Sep is the latest non-open month, so it carries Reopen.
    await userEvent.click(screen.getByRole('button', { name: 'Reopen' }));
    const confirmBtn = screen.getAllByRole('button', { name: 'Reopen' }).at(-1) as HTMLButtonElement;
    expect(confirmBtn.disabled).toBe(true);
    await userEvent.type(screen.getByLabelText(/Reason/), 'late bill');
    expect(confirmBtn.disabled).toBe(false);
    await userEvent.click(confirmBtn);
    expect(resources.reopenAccountingPeriod).toHaveBeenCalledWith(1, 'late bill');
  });

  it('previews the year-end close before it can be confirmed', async () => {
    wrap(<PeriodsPage />);
    await screen.findByText('Oct');
    await userEvent.click(screen.getByRole('button', { name: 'Close FY' }));
    expect(await screen.findByText(/Net profit/)).toBeTruthy();
    const dialogs = await screen.findAllByRole('dialog');
    const closeBtn = Array.from(dialogs[0].querySelectorAll('button')).find((b) => b.textContent === 'Close FY') as HTMLButtonElement;
    expect(closeBtn.disabled).toBe(true);
  });

  it('hides every close control from a report reader', async () => {
    auth.role = 'ACCOUNTANT';
    wrap(<PeriodsPage />);
    await screen.findByText('Oct');
    expect(screen.queryByRole('button', { name: 'Close period' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Soft-close' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Close FY' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Reopen' })).toBeNull();
  });
});
