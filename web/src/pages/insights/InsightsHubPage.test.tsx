import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import type { ReactElement } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { InsightsHubPage } from '@/pages/insights/InsightsHubPage';

const state = vi.hoisted(() => ({
  summary: {
    id: 1,
    summaryDate: '2026-10-20',
    narrative: 'A quiet counter.',
    stale: false,
    canGenerate: true,
    generatedAt: '2026-10-20T04:00:00Z',
    kpis: { salesTodayTotal: 10, salesMtdTotal: 20, receivables: 3, payables: 4, openAlerts: 1 },
  } as Record<string, unknown>,
  alertsFail: false,
}));

vi.mock('@/components/insights/AiConsentGate', () => ({
  useAiConsentOn: () => true,
  AiConsentOffScreen: () => null,
}));

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ user: { role: 'OWNER', canViewAiInsights: true, canUseAiAssistant: true, canViewFinancialReports: true, company: { aiFeaturesEnabled: true } } }),
}));

vi.mock('@/api/resources', () => ({
  getDailySummary: async () => state.summary,
  listBusinessAlerts: async () => {
    if (state.alertsFail) throw new Error('alerts are down');
    return [];
  },
  listGrowthHints: async () => [],
  generateDailySummary: vi.fn(),
}));

function wrap(ui: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('InsightsHubPage', () => {
  it('names the sales, receivables, and payables totals', async () => {
    wrap(<InsightsHubPage />);
    expect(await screen.findByText('A quiet counter.')).toBeTruthy();
    expect(screen.getByText('Sales today')).toBeTruthy();
    expect(screen.getByText('Sales MTD')).toBeTruthy();
    expect(screen.getByText('Receivables')).toBeTruthy();
    expect(screen.getByText('Payables')).toBeTruthy();
  });

  it('never reports "no alerts" when the alerts request failed', async () => {
    state.alertsFail = true;
    wrap(<InsightsHubPage />);
    expect(await screen.findByText(/Could not load alerts/)).toBeTruthy();
    expect(screen.queryByText('No open business alerts.')).toBeNull();
    state.alertsFail = false;
  });

  it('offers the owner a way to build the first summary', async () => {
    state.summary = { id: null, summaryDate: '2026-10-20', narrative: '', kpis: {}, canGenerate: true, stale: true };
    wrap(<InsightsHubPage />);
    expect(await screen.findByText('Generate summary')).toBeTruthy();
    expect(screen.getByText('No summary has been built yet.')).toBeTruthy();
  });
});
