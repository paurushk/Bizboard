import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { AttentionPage } from '@/pages/AttentionPage';

const { dismissAttentionRow, getLearningReport, listAttentionRows, snoozeAttentionRow } = vi.hoisted(() => ({
  listAttentionRows: vi.fn(async (..._args: unknown[]) => [{
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
  listAttentionRows: (...args: unknown[]) => listAttentionRows(...args),
  getLearningReport: () => getLearningReport(),
  dismissAttentionRow: (...args: unknown[]) => dismissAttentionRow(...args),
  snoozeAttentionRow: (...args: unknown[]) => snoozeAttentionRow(...args),
  assignAttentionRow: vi.fn(),
  listCompanyUsers: vi.fn(async () => []),
}));

describe('AttentionPage', () => {
  it('lists a problem and dismisses it without snoozing', async () => {
    const user = userEvent.setup();
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <AttentionPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(screen.queryByText(/Learning report/)).not.toBeInTheDocument();
    expect(await screen.findByText('Dead stock')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Dismiss' }));
    await waitFor(() => expect(dismissAttentionRow).toHaveBeenCalledWith('DEAD_STOCK:3'));
    expect(snoozeAttentionRow).not.toHaveBeenCalled();
  });

  it('asks why a possible duplicate payment is not one, and sends the reason', async () => {
    const user = userEvent.setup();
    listAttentionRows.mockResolvedValueOnce([{
      code: 'DUPLICATE_PAYMENT',
      severity: 'warning',
      title: 'Possible duplicate receipt',
      moneyImpactPaise: 10000,
      currency: 'INR',
      reason: '2 receipts',
      actionLabel: 'Review receipts',
      actionHref: '/sales/receipts',
      sourceTicket: 'B-05',
      entityRef: { type: 'customer', id: 4 },
      dedupeKey: 'DUPLICATE_PAYMENT:4:2026-10-01:100.00:none',
      firstSeen: '2026-10-01T00:00:00Z',
      snoozeUntil: null,
    }]);
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <AttentionPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByText('Possible duplicate receipt')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Dismiss' }));
    const confirm = screen.getAllByRole('button', { name: 'Dismiss' }).pop() as HTMLButtonElement;
    expect(confirm.disabled).toBe(true);
    expect(dismissAttentionRow).not.toHaveBeenCalledWith('DUPLICATE_PAYMENT:4:2026-10-01:100.00:none');
    await user.type(screen.getByLabelText(/why is this not a duplicate/i), 'two real payments');
    await user.click(confirm);
    await waitFor(() =>
      expect(dismissAttentionRow).toHaveBeenCalledWith('DUPLICATE_PAYMENT:4:2026-10-01:100.00:none', 'two real payments'),
    );
  });
});
