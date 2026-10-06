import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import type { ReactElement } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { BooksCloseSection } from '@/pages/phase/BooksCloseSection';

const state = vi.hoisted(() => ({ mode: 'ok' as 'ok' | 'slow' | 'fail' }));

vi.mock('@/api/resources', () => ({
  getAccountingReport: async (report: string) => {
    if (state.mode === 'slow') return new Promise(() => {});
    if (state.mode === 'fail') throw new Error('Ledger service unavailable');
    if (report === 'trial-balance') {
      return { totalDebit: '100.00', totalCredit: '100.00', balanced: true };
    }
    if (report === 'books-health') return { ar: { gl: '350.00' }, alerts: [] };
    return { income: '40.00' };
  },
}));

vi.mock('@/api/client', () => ({
  apiClient: { get: async () => ({ data: [{ customerName: 'Ravi', outstanding: '15.00' }] }) },
  unwrapData: (data: unknown) => data,
  getErrorMessage: (error: unknown) => (error instanceof Error ? error.message : 'Something went wrong'),
  getErrorCode: () => undefined,
  getErrorRequestId: () => undefined,
}));

function wrap(ui: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe('BooksCloseSection', () => {
  it('renders debit, credit, and whether they match', async () => {
    wrap(<BooksCloseSection />);
    expect(await screen.findByText(/Debit and credit match/)).toBeTruthy();
    expect(screen.getByText(/Trial balance debit/)).toBeTruthy();
    expect(screen.getByText(/Trial balance credit/)).toBeTruthy();
    expect(screen.getByText(/Profit and loss income/)).toBeTruthy();
    expect(await screen.findByText(/Accounts receivable control/)).toBeTruthy();
    expect(screen.queryByText(/Ravi/)).toBeNull();
  });

  it('says nothing about a match while the books are still loading', async () => {
    state.mode = 'slow';
    wrap(<BooksCloseSection />);
    expect(await screen.findByRole('progressbar')).toBeTruthy();
    expect(screen.queryByText(/do not match/)).toBeNull();
    expect(screen.queryByText(/Accounts receivable control/)).toBeNull();
    state.mode = 'ok';
  });

  it('shows an error with a retry instead of a false mismatch when the books fail to load', async () => {
    state.mode = 'fail';
    wrap(<BooksCloseSection />);
    await waitFor(() => expect(screen.getByText(/Ledger service unavailable/)).toBeTruthy());
    expect(screen.getByRole('button', { name: /try again|retry/i })).toBeTruthy();
    expect(screen.queryByText(/do not match/)).toBeNull();
    state.mode = 'ok';
  });
});
