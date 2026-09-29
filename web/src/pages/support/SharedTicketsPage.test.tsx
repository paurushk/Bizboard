import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import type { ReactElement } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { isSupportTicketsEnabled } from '@/config/features';
import { SharedTicketsPage } from '@/pages/support/SharedTicketsPage';

vi.mock('@/config/features', () => ({ isSupportTicketsEnabled: vi.fn(() => false) }));
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
});
