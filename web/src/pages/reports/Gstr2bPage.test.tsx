import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { Gstr2bPage } from '@/pages/reports/Gstr2bPage';

vi.mock('@/api/gstr2b', async () => {
  const actual = await vi.importActual<typeof import('@/api/gstr2b')>('@/api/gstr2b');
  return {
    ...actual,
    listGstr2bPage: vi.fn(async () => ({ results: [], count: 0, next: null, previous: null })),
    fetchImsSummary: vi.fn(async () => ({
      period: '2026-09',
      totalItc: '10.00',
      matchedItc: '4.00',
      unresolvedItc: '3.00',
      itcAtRisk: '3.00',
      expiringItc: '1.00',
      expiringCount: 1,
      ineligibleItc: '2.50',
    })),
    fetchImsScorecard: vi.fn(async () => ({ period: '2026-09', suppliers: [] })),
  };
});

describe('Gstr2bPage ineligible ITC', () => {
  it('shows the ineligible amount from the summary', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <Gstr2bPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    const label = await screen.findByText('Ineligible ITC');
    await waitFor(() => {
      expect(label.closest('.MuiPaper-root')?.textContent).toMatch(/2\.50/);
    });
  });
});
