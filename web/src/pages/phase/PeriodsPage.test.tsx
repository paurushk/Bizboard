import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import type { ReactElement } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { PeriodsPage } from '@/pages/phase/PeriodsPage';

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

vi.mock('@/api/resources', () => ({
  listAccountingPeriods: async () => [{
    id: 1, name: 'Sep', startDate: '2026-09-01', endDate: '2026-09-30', status: 'OPEN',
  }],
  getAccountingReport: async (report: string) => {
    if (report === 'trial-balance') return { totalDebit: '100.00', totalCredit: '100.00', balanced: true };
    return { income: '40.00' };
  },
  createAccountingPeriod: vi.fn(),
  closeAccountingPeriod: vi.fn(),
  softCloseAccountingPeriod: vi.fn(),
  softCloseGstPeriod: vi.fn(),
  closeFinancialYear: vi.fn(),
}));

vi.mock('@/api/client', () => ({
  apiClient: { get: async () => ({ data: [{ customerName: 'Ravi', outstanding: '15.00' }] }) },
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

describe('PeriodsPage close control', () => {
  it('lets an owner read the books and close the period', async () => {
    auth.role = 'OWNER';
    wrap(<PeriodsPage />);
    expect(await screen.findByText(/Debit and credit match/)).toBeTruthy();
    expect(screen.getByRole('button', { name: /^Close$/ })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Soft-close' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Close FY' })).toBeTruthy();
  });

  it('lets a report reader see the books and hides close', async () => {
    auth.role = 'ACCOUNTANT';
    wrap(<PeriodsPage />);
    expect(await screen.findByText(/Debit and credit match/)).toBeTruthy();
    expect(await screen.findByText(/Ravi/)).toBeTruthy();
    expect(screen.queryByRole('button', { name: /^Close$/ })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Soft-close' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Close FY' })).toBeNull();
  });
});
