import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactElement } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { JournalsPage } from '@/pages/phase/JournalsPage';

const auth = vi.hoisted(() => ({ role: 'OWNER', canPostJournals: true }));

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ user: { id: 1, role: auth.role, canPostJournals: auth.canPostJournals } }),
}));

vi.mock('@/hooks/useSubscriptionGate', () => ({
  useSubscriptionGate: () => ({ writesBlocked: false, isLoading: false }),
}));

vi.mock('@/api/resources', () => ({
  listJournals: async () => [
    { id: 1, number: 'JV-1', entryDate: '2026-09-01', status: 'DRAFT', narration: 'Rent' },
    {
      id: 2, number: 'JV-2', entryDate: '2026-09-02', status: 'POSTED', narration: 'Rent paid',
      sourceType: 'MANUAL_JOURNAL', sourceLabel: 'a manual journal', sourcePath: null, canReverse: true,
    },
    {
      id: 3, number: 'JV-3', entryDate: '2026-09-03', status: 'POSTED', narration: 'Sales',
      sourceType: 'SALES_INVOICE', sourceId: 7, sourceLabel: 'a sales invoice', sourcePath: '/sales/history/7', canReverse: false,
    },
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
  beforeEach(() => {
    auth.role = 'OWNER';
    auth.canPostJournals = true;
  });

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

  it('offers Reverse only on manual journals and links a system journal to its document', async () => {
    wrap(<JournalsPage />);
    expect(await screen.findByText('JV-3')).toBeTruthy();
    // JV-2 (manual) is the only row with a Reverse button; JV-3 came from a sales invoice.
    expect(screen.getAllByRole('button', { name: 'Reverse' })).toHaveLength(1);
    const link = screen.getByRole('link', { name: 'a sales invoice' });
    expect(link.getAttribute('href')).toBe('/sales/history/7');
  });

  it('disables posting actions for a user without journal-posting rights', async () => {
    auth.role = 'STAFF';
    auth.canPostJournals = false;
    wrap(<JournalsPage />);
    expect(await screen.findByText('JV-1')).toBeTruthy();
    expect((screen.getByRole('button', { name: 'New voucher' }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole('button', { name: 'Post' }) as HTMLButtonElement).disabled).toBe(true);
  });
});
