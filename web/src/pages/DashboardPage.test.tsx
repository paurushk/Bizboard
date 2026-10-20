import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import type { ReactElement } from 'react';
import axe from 'axe-core';
import { beforeEach, describe, expect, it, vi } from 'vitest';
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
  receivablesAging: { current: '0', days130: '0', days3160: '0', days6190: '0', days90Plus: '0' },
  receivablesUnclearedCheques: '250.00',
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
vi.mock('@/components/OnboardingChecklist', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/components/OnboardingChecklist')>()),
  OnboardingChecklist: () => null,
}));
vi.mock('@/pages/AttentionPage', () => ({ AttentionQueuePreview: () => <div>attention-preview</div> }));
vi.mock('@/components/CollectionAttentionCard', () => ({ CollectionAttentionCard: () => null }));
const { listLowStock, getDashboard } = vi.hoisted(() => ({
  getDashboard: vi.fn(),
  listLowStock: vi.fn(async () => [] as Array<{ productName: string; available: number; reorderLevel: number }>),
}));

vi.mock('@/api/resources', () => ({
  getDashboard: () => getDashboard(),
  getCompany: async () => ({ id: 9, name: 'Acme', onboarding: { activationDone: true } }),
  listLowStock: () => listLowStock(),
  getDailySummary: vi.fn(async () => ({})),
  listBusinessAlerts: vi.fn(async () => []),
  getBusinessHealth: vi.fn(async () => ({ score: 80, grade: 'A' })),
}));

beforeEach(() => {
  listLowStock.mockClear();
  getDashboard.mockReset();
  getDashboard.mockResolvedValue(DASHBOARD_DATA);
});

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

  it('no longer shows counter diagnostics on the home screen', async () => {
    wrap(<DashboardPage />);
    await screen.findByText('INV-0001');
    expect(screen.queryByText('Counter diagnostics')).toBeNull();
  });

  it('says which timezone today and this month follow', async () => {
    wrap(<DashboardPage />);
    expect(await screen.findByText(/follow India time/i)).toBeInTheDocument();
  });

  it('offers the invite prompt only once the checklist is done', async () => {
    getDashboard.mockResolvedValue({ ...DASHBOARD_DATA, productCount: 1, invoiceCount: 1 });
    wrap(<DashboardPage />);
    expect(await screen.findByText(/invite/i, { selector: '.MuiAlert-message, .MuiAlert-message *' })).toBeInTheDocument();
  });

  it('shows the low-stock count and rows from the dashboard payload without asking for the list again', async () => {
    getDashboard.mockResolvedValue({
      ...DASHBOARD_DATA,
      lowStockCount: 7,
      lowStockItems: [
        { product: 1, productName: 'Tea', available: 1, reorderLevel: 5 },
        { product: 2, productName: 'Rice', available: 0, reorderLevel: 2 },
      ],
    });
    wrap(<DashboardPage />);
    const label = await screen.findByText('Low stock', { selector: 'p, span, div' });
    const card = label.closest('.MuiPaper-root');
    expect(card).toBeTruthy();
    expect(within(card as HTMLElement).getByText('7')).toBeTruthy();
    expect(await screen.findByText(/Tea/)).toBeTruthy();
    expect(listLowStock).not.toHaveBeenCalled();
  });

  it('falls back to the stock-alert list for a response without the rows', async () => {
    listLowStock.mockResolvedValueOnce([
      { productName: 'Tea', available: 1, reorderLevel: 5 },
      { productName: 'Rice', available: 0, reorderLevel: 2 },
    ]);
    wrap(<DashboardPage />);
    const label = await screen.findByText('Low stock', { selector: 'p, span, div' });
    const card = label.closest('.MuiPaper-root');
    await waitFor(() => expect(within(card as HTMLElement).getByText('2')).toBeTruthy());
  });

  it('does not claim stock is healthy when the dashboard could not load', async () => {
    getDashboard.mockRejectedValue(new Error('boom'));
    wrap(<DashboardPage />);
    await screen.findByText('attention-preview');
    expect(screen.queryByText(/stock is healthy|nothing is low/i)).toBeNull();
    expect(screen.queryByRole('heading', { name: 'Low stock' })).toBeNull();
  });

  it('says how much of the receivable is in cheques that have not cleared', async () => {
    wrap(<DashboardPage />);
    expect(await screen.findByText(/includes .*250\.00.* in cheques that have not cleared/i)).toBeTruthy();
  });

  it('keeps the attention preview when the dashboard KPIs fail to load', async () => {
    getDashboard.mockRejectedValue(new Error('boom'));
    wrap(<DashboardPage />);
    expect(await screen.findByText('attention-preview')).toBeInTheDocument();
    expect(screen.queryByText('INV-0001')).toBeNull();
    expect(await screen.findByRole('button', { name: /retry|try again/i })).toBeInTheDocument();
  });

  it('survives blocked localStorage', async () => {
    const spy = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('SecurityError');
    });
    wrap(<DashboardPage />);
    expect(await screen.findByText('INV-0001')).toBeInTheDocument();
    spy.mockRestore();
  });

  it('has no accessibility violations', async () => {
    wrap(<DashboardPage />);
    await screen.findByText('INV-0001');
    const results = await axe.run(document.body, {
      rules: { 'color-contrast': { enabled: false }, region: { enabled: false } },
    });
    expect(results.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(' ')).join(' | ')}`)).toEqual([]);
  });
});
