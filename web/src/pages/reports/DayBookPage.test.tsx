import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import type { ReactElement } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { DayBookPage } from '@/pages/reports/DayBookPage';

vi.mock('@/api/resources', () => ({
  getDayBook: async () => ({
    date: '2026-09-21',
    inflow: '200',
    outflow: '50',
    net: '150',
    disclaimer: 'Cheque receipts count only when CLEARED. This is not a Cash Book relabel.',
    rows: [{ id: 1, date: '2026-09-21', txnType: 'PAYMENT_IN', number: 'RCT-1', party: 'Ravi', amount: '200', status: 'POSTED' }],
  }),
}));

function wrap(ui: ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('DayBookPage', () => {
  it('shows cash-position KPIs and the cheque-cleared disclaimer', async () => {
    wrap(<DayBookPage />);
    expect(await screen.findByText(/cheque receipts count only when cleared/i)).toBeTruthy();
    expect(screen.getByText('Inflow')).toBeTruthy();
    expect(screen.getByText('RCT-1')).toBeTruthy();
  });
});
