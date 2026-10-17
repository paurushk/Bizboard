import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
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

const rows = [
    { id: 1, number: 'JV-1', entryDate: '2026-09-01', status: 'DRAFT', narration: 'Rent' },
    {
      id: 2, number: 'JV-2', entryDate: '2026-09-02', status: 'POSTED', narration: 'Rent paid',
      sourceType: 'MANUAL_JOURNAL', sourceLabel: 'a manual journal', sourcePath: null, canReverse: true,
    },
    {
      id: 3, number: 'JV-3', entryDate: '2026-09-03', status: 'POSTED', narration: 'Sales',
      sourceType: 'SALES_INVOICE', sourceId: 7, sourceLabel: 'a sales invoice', sourcePath: '/sales/history/7', canReverse: false,
    },
];

const apiMock = vi.hoisted(() => ({
  discardJournal: vi.fn(async () => undefined),
  exportJournals: vi.fn(async () => new Blob(['x'])),
  listJournalsPage: vi.fn(),
}));

vi.mock('@/api/resources', () => ({
  listJournalsPage: (...args: unknown[]) => apiMock.listJournalsPage(...args),
  listAccounts: async () => [],
  listCostCenters: async () => [],
  listCustomers: async () => [],
  listSuppliers: async () => [],
  createJournal: vi.fn(),
  updateJournal: vi.fn(),
  discardJournal: (...args: unknown[]) => apiMock.discardJournal(...(args as [number])),
  exportJournals: (...args: unknown[]) => apiMock.exportJournals(...(args as [])),
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
    apiMock.listJournalsPage.mockReset();
    apiMock.listJournalsPage.mockResolvedValue({ results: rows, count: rows.length, next: null, previous: null });
    auth.role = 'OWNER';
    auth.canPostJournals = true;
  });

  it('explains that posting writes the voucher into the books', async () => {
    wrap(<JournalsPage />);
    expect(await screen.findByText('JV-1')).toBeTruthy();
    await userEvent.click(screen.getByRole('button', { name: 'Post' }));
    expect(await screen.findByText(/Posting writes this voucher into your books\./)).toBeTruthy();
  });

  it('explains that reverse writes an opposite entry and keeps the first voucher', async () => {
    wrap(<JournalsPage />);
    expect(await screen.findByText('JV-2')).toBeTruthy();
    await userEvent.click(screen.getByRole('button', { name: 'Reverse' }));
    expect(
      await screen.findByText(
        /Reverse with an opposite entry\. The first voucher stays in the books\. This cannot be undone from this screen\./,
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

  it('discards a draft after confirmation', async () => {
    wrap(<JournalsPage />);
    expect(await screen.findByText('JV-1')).toBeTruthy();
    await userEvent.click(screen.getByRole('button', { name: 'Discard' }));
    expect(await screen.findByText(/Its number is kept/)).toBeTruthy();
    await userEvent.click(screen.getAllByRole('button', { name: 'Discard' }).at(-1)!);
    await waitFor(() => expect(apiMock.discardJournal).toHaveBeenCalledWith(1));
  });

  it('opens the detail drawer with the lines', async () => {
    apiMock.listJournalsPage.mockResolvedValue({
      results: [{
        id: 9, number: 'JV-9', entryDate: '2026-09-09', status: 'POSTED', narration: 'Detail me',
        lines: [{ id: 1, account: 1, accountCode: '1100', accountName: 'Cash', debit: '50.00', credit: '0.00' }],
      }],
      count: 1, next: null, previous: null,
    });
    wrap(<JournalsPage />);
    expect(await screen.findByText('JV-9')).toBeTruthy();
    await userEvent.click(screen.getByRole('button', { name: /View JV-9/ }));
    expect(await screen.findByText(/1100 Cash/)).toBeTruthy();
  });

  it('sends the search text to the server and shows the no-match message', async () => {
    wrap(<JournalsPage />);
    expect(await screen.findByText('JV-1')).toBeTruthy();
    apiMock.listJournalsPage.mockResolvedValue({ results: [], count: 0, next: null, previous: null });
    await userEvent.type(screen.getByLabelText('Search narration or reference'), 'zzz');
    expect(await screen.findByText('No journals match these filters.')).toBeTruthy();
    expect(apiMock.listJournalsPage.mock.calls.at(-1)?.[0]).toMatchObject({ q: 'zzz' });
  });
});
