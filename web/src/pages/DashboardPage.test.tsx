import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import type { ReactElement } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { DashboardPage } from '@/pages/DashboardPage';

// G-17: the "Recent sales" widget's badge duplicates the same client-side
// precedence logic as SalesHistoryPage/InvoiceDetailPage — pin the same
// fully-returned-shows-as-Paid regression here too, since it's a third,
// independently-rendered surface fed by the dashboard's own recent_invoices
// payload (reporting/services.py), not the invoice list endpoint.
const DASHBOARD_DATA = {
  salesToday: { total: '0', count: 0 },
  salesThisMonth: { total: '104', count: 1 },
  purchasesThisMonth: { total: '0', count: 0 },
  receivables: '0',
  payables: '0',
  lowStockCount: 0,
  cashPosition: { total: '0' },
  productCount: 1,
  invoiceCount: 1,
  recentInvoices: [
    {
      id: 1,
      number: 'INV-0001',
      customer: 'Cash',
      date: '2026-09-12',
      status: 'RETURNED',
      grandTotal: '104.00',
      balance: '0',
      paymentState: 'PAID',
      returnState: 'FULL',
    },
  ],
};

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 1, email: 'owner@x.test', fullName: 'Owner', role: 'OWNER', companyId: 9 },
  }),
}));

vi.mock('@/onboarding/shouldForceSetup', () => ({ shouldForceSetup: () => false }));
vi.mock('@/components/OnboardingChecklist', () => ({ OnboardingChecklist: () => null }));
vi.mock('@/pages/AttentionPage', () => ({ AttentionQueuePreview: () => null }));
vi.mock('@/components/CollectionAttentionCard', () => ({ CollectionAttentionCard: () => null }));
vi.mock('@/lib/telemetry', () => ({
  getShopFloorSummary: vi.fn(async () => ({
    days: 7,
    completeP95Ms: 410,
    offlineFlushFail: 0,
    funnel: {
      invoiceCompleteStarted: 10,
      invoiceComplete: 8,
      invoiceCompleteFailed: 2,
      invoiceCompleteFailedByReason: { validation: 1, '5xx': 1, timeout: 0, offline: 0, help_code: 0, unknown: 0 },
      pdfStarted: 8,
      pdfFailed: 1,
      paymentStarted: 3,
      paymentCompleted: 3,
      paymentFailed: 0,
      signupCompleted: 1,
      signupFailed: 0,
    },
  })),
  funnelCount: (funnel: Record<string, unknown> | undefined, snake: string, camel: string) => {
    const v = funnel?.[camel] ?? funnel?.[snake];
    return typeof v === 'number' ? v : 0;
  },
  funnelReasons: (funnel: Record<string, unknown> | undefined, snake: string, camel: string) => {
    const v = funnel?.[camel] ?? funnel?.[snake];
    return v && typeof v === 'object' ? v : {};
  },
}));

vi.mock('@/api/resources', () => ({
  getDashboard: async () => DASHBOARD_DATA,
  getCompany: async () => ({ id: 9, name: 'Acme', onboarding: { activationDone: true } }),
  listLowStock: async () => [],
  getDailySummary: vi.fn(async () => ({})),
  listBusinessAlerts: vi.fn(async () => []),
  getBusinessHealth: vi.fn(async () => ({ score: 80, grade: 'A' })),
}));

function wrap(ui: ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('DashboardPage recent-sales badge — G-17', () => {
  it('shows Returned, not Paid, for a fully-returned invoice in the recent-sales widget', async () => {
    wrap(<DashboardPage />);
    const row = (await screen.findByText('INV-0001')).closest('tr');
    expect(row).toBeTruthy();
    expect(within(row as HTMLElement).getByText(/returned/i)).toBeTruthy();
    expect(within(row as HTMLElement).queryByText(/^paid$/i)).toBeNull();
  });

  it('shows Complete started / completed / failed and the reason split', async () => {
    wrap(<DashboardPage />);
    expect(await screen.findByText('Invoice Complete')).toBeInTheDocument();
    expect(screen.getByText('Started')).toBeInTheDocument();
    expect(screen.getByText('10')).toBeInTheDocument();
    expect(screen.getByText('validation: 1')).toBeInTheDocument();
    expect(screen.getByText('5xx: 1')).toBeInTheDocument();
  });
});
