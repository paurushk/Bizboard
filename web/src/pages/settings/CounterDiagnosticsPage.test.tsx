import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { CounterDiagnosticsPage } from '@/pages/settings/CounterDiagnosticsPage';

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

describe('CounterDiagnosticsPage', () => {
  it('shows Complete started / completed / failed and the reason split', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <CounterDiagnosticsPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByText('Invoice Complete')).toBeInTheDocument();
    expect(screen.getByText('Started')).toBeInTheDocument();
    expect(screen.getByText('10')).toBeInTheDocument();
    expect(screen.getByText('Invalid input: 1')).toBeInTheDocument();
    expect(screen.getByText('Server error: 1')).toBeInTheDocument();
  });
});
