import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import type { ReactElement } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { BooksCloseSection } from '@/pages/phase/BooksCloseSection';

vi.mock('@/api/resources', () => ({
  getAccountingReport: async (report: string) => {
    if (report === 'trial-balance') {
      return { totalDebit: '100.00', totalCredit: '100.00', balanced: true };
    }
    return { income: '40.00' };
  },
}));

vi.mock('@/api/client', () => ({
  apiClient: { get: async () => ({ data: [{ customerName: 'Ravi', outstanding: '15.00' }] }) },
  unwrapData: (data: unknown) => data,
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
    expect(await screen.findByText(/Ravi/)).toBeTruthy();
  });
});
