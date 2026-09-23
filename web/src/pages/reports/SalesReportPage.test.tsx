import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import type { ReactElement } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { SalesReportPage } from '@/pages/reports/SalesReportPage';

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 1, email: 'owner@x.test', fullName: 'Owner', role: 'OWNER', companyId: 9 },
  }),
}));

vi.mock('@/api/resources', () => ({
  getSalesRegister: async () => ({ rows: [] }),
  getSalesSummary: async () => ({
    totals: { revenue: '200', invoiceCount: 2 },
    topCustomers: [],
    topProducts: [],
    paymentBreakdown: {
      paid: { count: 0, amount: '0' },
      partial: { count: 0, amount: '0' },
      unpaid: { count: 2, amount: '200' },
    },
    byDate: [{ invoiceDate: '2026-09-21', revenue: '200', count: 2 }],
  }),
  exportReport: vi.fn(),
}));

function wrap(ui: ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('SalesReportPage revenue by date', () => {
  it('renders the by-date revenue table', async () => {
    wrap(<SalesReportPage />);
    expect(await screen.findByText('Revenue by date')).toBeTruthy();
    expect(screen.getByText('2026-09-21')).toBeTruthy();
  });
});
