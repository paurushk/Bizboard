import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import type { ReactElement } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { listJobCards } from '@/api/roadmap';
import { isWorkshopEnabled } from '@/config/features';
import { JobCardsPage } from '@/pages/workshop/JobCardsPage';

vi.mock('@/config/features', () => ({ isWorkshopEnabled: vi.fn(() => false) }));
vi.mock('@/api/roadmap', () => ({
  listJobCards: vi.fn().mockResolvedValue({ results: [] }),
  createJobCard: vi.fn(),
  convertJobCard: vi.fn(),
}));
vi.mock('@/pages/growth/widgets', () => ({ CustomerField: () => null }));

function wrap(ui: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('JobCardsPage', () => {
  it('explains that the module is off', () => {
    vi.mocked(isWorkshopEnabled).mockReturnValue(false);
    wrap(<JobCardsPage />);
    expect(screen.getByText(/isn’t enabled/i)).toBeTruthy();
  });

  it('shows create when the module is on and the list is empty', async () => {
    vi.mocked(isWorkshopEnabled).mockReturnValue(true);
    wrap(<JobCardsPage />);
    expect(await screen.findByRole('button', { name: 'Create' })).toBeTruthy();
  });

  it('shows earlier job number, status, and date, and says when the list stopped at 20', async () => {
    vi.mocked(isWorkshopEnabled).mockReturnValue(true);
    vi.mocked(listJobCards).mockResolvedValue({
      results: [{
        id: 2,
        number: 'JC-2',
        status: 'OPEN',
        serialHistory: [{
          serialId: 5,
          capped: true,
          jobs: [{ id: 1, number: 'JC-1', status: 'COMPLETED', date: '2026-08-01' }],
        }],
      }],
    } as never);
    wrap(<JobCardsPage />);
    expect(await screen.findByText(/JC-1/)).toBeTruthy();
    expect(screen.getByText(/Status: COMPLETED/)).toBeTruthy();
    expect(screen.getByText(/Date: 2026-08-01/)).toBeTruthy();
    expect(screen.getByText(/Showing the 20 newest earlier jobs/)).toBeTruthy();
  });
});
