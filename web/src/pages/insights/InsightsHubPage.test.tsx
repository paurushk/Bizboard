import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import type { ReactElement } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { InsightsHubPage } from '@/pages/insights/InsightsHubPage';

vi.mock('@/components/insights/AiConsentGate', () => ({
  useAiConsentOn: () => true,
  AiConsentOffScreen: () => null,
}));

vi.mock('@/api/resources', () => ({
  getDailySummary: async () => ({
    narrative: 'A quiet counter.',
    kpis: {
      salesTodayTotal: 10,
      salesMtdTotal: 20,
      receivables: 3,
      payables: 4,
      openAlerts: 1,
    },
  }),
  listBusinessAlerts: async () => [],
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

describe('InsightsHubPage labels', () => {
  it('names the sales, receivables, and payables totals', async () => {
    wrap(<InsightsHubPage />);
    expect(await screen.findByText('A quiet counter.')).toBeTruthy();
    expect(screen.getByText('Sales today')).toBeTruthy();
    expect(screen.getByText('Sales MTD')).toBeTruthy();
    expect(screen.getByText('Receivables')).toBeTruthy();
    expect(screen.getByText('Payables')).toBeTruthy();
  });
});
