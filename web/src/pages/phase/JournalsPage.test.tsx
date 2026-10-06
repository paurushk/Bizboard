import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactElement } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { JournalsPage } from '@/pages/phase/JournalsPage';

vi.mock('@/hooks/useSubscriptionGate', () => ({
  useSubscriptionGate: () => ({ writesBlocked: false, isLoading: false }),
}));

vi.mock('@/api/resources', () => ({
  listJournals: async () => [
    { id: 1, number: 'JV-1', entryDate: '2026-09-01', status: 'DRAFT', narration: 'Rent' },
    { id: 2, number: 'JV-2', entryDate: '2026-09-02', status: 'POSTED', narration: 'Sales' },
  ],
  listAccounts: async () => [],
  createJournal: vi.fn(),
  postJournal: vi.fn(),
  reverseJournal: vi.fn(),
}));

function wrap(ui: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('JournalsPage post and reverse copy', () => {
  it('explains that posting writes the voucher into the books', async () => {
    wrap(<JournalsPage />);
    expect(await screen.findByText('JV-1')).toBeTruthy();
    await userEvent.click(screen.getByRole('button', { name: 'Post' }));
    expect(await screen.findByText('Posting writes this voucher into your books.')).toBeTruthy();
  });

  it('explains that reverse writes an opposite entry and keeps the first voucher', async () => {
    wrap(<JournalsPage />);
    expect(await screen.findByText('JV-2')).toBeTruthy();
    await userEvent.click(screen.getByRole('button', { name: 'Reverse' }));
    expect(
      await screen.findByText(
        'Reverse with an opposite entry. The first voucher stays in the books. This cannot be undone from this screen.',
      ),
    ).toBeTruthy();
  });
});
