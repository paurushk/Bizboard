import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { AttentionPage } from '@/pages/AttentionPage';

const { dismissAttentionRow, getLearningReport, snoozeAttentionRow } = vi.hoisted(() => ({
  dismissAttentionRow: vi.fn(async () => ({ dedupeKey: 'DEAD_STOCK:3', dismissed: true })),
  getLearningReport: vi.fn(async () => ({
    acted: 2, metricImproved: 1, windowDays: 7, thresholdsChanged: false,
  })),
  snoozeAttentionRow: vi.fn(async () => ({})),
}));

vi.mock('@/config/featureFlags', () => ({
  useFeatureFlagEpoch: () => 0,
  isRuntimeFlagEnabled: () => false,
}));

vi.mock('@/api/resources', () => ({
  listAttentionRows: vi.fn(async () => [{
    code: 'DEAD_STOCK',
    severity: 'warning',
    title: 'Dead stock',
    moneyImpactPaise: 10000,
    currency: 'INR',
    reason: 'No sales',
    actionLabel: 'Fix',
    actionHref: '/inventory/products',
    sourceTicket: 'B-05',
    entityRef: { type: 'product', id: 3 },
    dedupeKey: 'DEAD_STOCK:3',
    firstSeen: '2026-09-20T00:00:00Z',
    snoozeUntil: null,
  }]),
  getLearningReport: () => getLearningReport(),
  dismissAttentionRow: (...args: unknown[]) => dismissAttentionRow(...args),
  snoozeAttentionRow: (...args: unknown[]) => snoozeAttentionRow(...args),
  assignAttentionRow: vi.fn(),
  listCompanyUsers: vi.fn(async () => []),
}));

describe('AttentionPage', () => {
  it('shows the learning report and dismisses a row without snoozing it', async () => {
    const user = userEvent.setup();
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <AttentionPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByText(/Learning report/)).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText(/Learning report/).textContent).toMatch(/Acted inside 7 days\s+2/);
      expect(screen.getByText(/Learning report/).textContent).toMatch(/Metric improved\s+1/);
    });
    expect(await screen.findByText('Dead stock')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Dismiss' }));
    await waitFor(() => expect(dismissAttentionRow).toHaveBeenCalledWith('DEAD_STOCK:3'));
    expect(snoozeAttentionRow).not.toHaveBeenCalled();
  });
});
