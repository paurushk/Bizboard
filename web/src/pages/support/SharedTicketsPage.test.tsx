import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import type { ReactElement } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { listSharedTickets } from '@/api/roadmap';
import { isSupportTicketsEnabled } from '@/config/features';
import { SharedTicketsPage } from '@/pages/support/SharedTicketsPage';

vi.mock('@/config/features', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/config/features')>();
  return {
    ...actual,
    isSupportTicketsEnabled: vi.fn(() => false),
  };
});
vi.mock('@/api/roadmap', () => ({
  listSharedTickets: vi.fn().mockResolvedValue({ results: [] }),
}));

function wrap(ui: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('SharedTicketsPage', () => {
  it('explains that the module is off', () => {
    vi.mocked(isSupportTicketsEnabled).mockReturnValue(false);
    wrap(<SharedTicketsPage />);
    expect(screen.getByText(/isn’t enabled/i)).toBeTruthy();
  });

  it('shows an empty list without a description block', async () => {
    vi.mocked(isSupportTicketsEnabled).mockReturnValue(true);
    wrap(<SharedTicketsPage />);
    expect(await screen.findByText('No shared tickets.')).toBeTruthy();
    expect(screen.queryByText(/description/i)).toBeNull();
  });

  it('shows a shared ticket status in plain language', async () => {
    vi.mocked(isSupportTicketsEnabled).mockReturnValue(true);
    vi.mocked(listSharedTickets).mockResolvedValueOnce({
      results: [
        {
          id: 1,
          sourceNumber: 'T-1',
          sourceCompanyName: 'Pilot',
          subject: 'Late delivery',
          status: 'OPEN',
        },
      ],
    });
    wrap(<SharedTicketsPage />);
    expect(await screen.findByText('T-1 · Pilot · Late delivery · Open')).toBeTruthy();
  });

  it('shows an error instead of an empty list when shared tickets fail to load', async () => {
    vi.mocked(isSupportTicketsEnabled).mockReturnValue(true);
    vi.mocked(listSharedTickets).mockRejectedValueOnce(new Error('tickets down'));
    wrap(<SharedTicketsPage />);
    expect(await screen.findByText('tickets down')).toBeTruthy();
    expect(screen.queryByText('No shared tickets.')).toBeNull();
  });
});
