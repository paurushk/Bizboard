import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { BankReconPage } from '@/pages/phase/BankingPhasePages';

const m = vi.hoisted(() => ({
  getPaymentHealth: vi.fn(async () => ({ unmatchedAging: {}, alerts: [] })),
  listRecon: vi.fn(),
  listReconNeedsReview: vi.fn(),
  matchReconReturn: vi.fn(async (..._args: unknown[]) => ({})),
}));

vi.mock('@/api/resources', () => ({
  getPaymentHealth: () => m.getPaymentHealth(),
  listRecon: () => m.listRecon(),
  listReconNeedsReview: () => m.listReconNeedsReview(),
  matchReconReturn: (...args: unknown[]) => m.matchReconReturn(...args),
  confirmRecon: vi.fn(),
  bulkAcceptExactMatches: vi.fn(),
  createReceiptFromReconLine: vi.fn(),
  listCustomersPage: async () => ({
    results: [
      { id: 1, name: 'Named Customer', isPosWalkIn: false },
      { id: 2, name: 'Walk-in', isPosWalkIn: true },
    ],
    count: 2, next: null, previous: null,
  }),
}));
vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ user: { id: 1, email: 'o@x.test', fullName: 'O', role: 'OWNER', companyId: 9 } }),
}));
vi.mock('@/hooks/useSubscriptionGate', () => ({ useSubscriptionGate: () => ({ writesBlocked: false }) }));

function wrap(ui: React.ReactElement, path = '/') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('Bank reconciliation: bounced cheques', () => {
  const REVIEW = [{
    match: 5, line: 11, lineDate: '2026-10-01', lineAmount: '100.00', bankAccount: 'HDFC',
    receipt: 44, receiptNumber: 'RCT-0044', customerName: 'Ravi Traders', reason: 'bounced',
  }];

  it('offers the matching debit line for a bounced cheque and matches it', async () => {
    m.listReconNeedsReview.mockResolvedValue(REVIEW);
    m.listRecon.mockResolvedValue([
      { line: { id: 90, txnDate: '2026-10-03', amount: '-100.00', narration: 'CHQ RETURN', matchStatus: 'UNMATCHED' }, suggestions: [] },
    ]);
    wrap(<BankReconPage />);
    expect(await screen.findByText('Bounced cheques to review')).toBeTruthy();
    expect(screen.getByText(/RCT-0044/)).toBeTruthy();
    await userEvent.click(screen.getByRole('button', { name: /match return line/i }));
    await waitFor(() => expect(m.matchReconReturn).toHaveBeenCalledWith({ line: 90, receipt: 44 }));
  });

  it('says so when no debit line of that amount is on the statement yet', async () => {
    m.listReconNeedsReview.mockResolvedValue(REVIEW);
    m.listRecon.mockResolvedValue([
      { line: { id: 91, txnDate: '2026-10-03', amount: '-55.00', narration: 'other', matchStatus: 'UNMATCHED' }, suggestions: [] },
    ]);
    wrap(<BankReconPage />);
    expect(await screen.findByText(/no unmatched debit line of this amount/i)).toBeTruthy();
    expect(screen.queryByRole('button', { name: /match return line/i })).toBeNull();
  });

  it('does not show the review panel when nothing needs review', async () => {
    m.listReconNeedsReview.mockResolvedValue([]);
    m.listRecon.mockResolvedValue([]);
    wrap(<BankReconPage />);
    await screen.findByText(/no unmatched bank lines/i);
    expect(screen.queryByText('Bounced cheques to review')).toBeNull();
  });

  it('keeps the walk-in customer out of the create-receipt picker', async () => {
    m.listReconNeedsReview.mockResolvedValue([]);
    m.listRecon.mockResolvedValue([
      { line: { id: 92, txnDate: '2026-10-03', amount: '300.00', narration: 'NEFT', matchStatus: 'UNMATCHED' }, suggestions: [] },
    ]);
    wrap(<BankReconPage />);
    await userEvent.click(await screen.findByRole('button', { name: /create receipt/i }));
    const dialog = await screen.findByRole('dialog');
    await userEvent.click(within(dialog).getByRole('combobox'));
    expect(await screen.findByRole('option', { name: 'Named Customer' })).toBeTruthy();
    expect(screen.queryByRole('option', { name: 'Walk-in' })).toBeNull();
  });
});

describe('Bank reconciliation opened from the Money hub', () => {
  const credit = { line: { id: 1, txnDate: '2026-10-03', amount: '1000.00', narration: 'NEFT IN', matchStatus: 'UNMATCHED' }, suggestions: [] };
  const debit = { line: { id: 2, txnDate: '2026-10-04', amount: '-400.00', narration: 'CHQ OUT', matchStatus: 'UNMATCHED' }, suggestions: [] };

  it('shows only the bank credits when the money-in tile sends the user here', async () => {
    m.listReconNeedsReview.mockResolvedValue([]);
    m.listRecon.mockResolvedValue([credit, debit]);
    wrap(<BankReconPage />, '/payments/reconciliation?direction=credit&via=money');
    expect(await screen.findByText('NEFT IN')).toBeTruthy();
    expect(screen.queryByText('CHQ OUT')).toBeNull();
    expect(screen.getByText('Opened from Money: Bank credits not matched')).toBeTruthy();
  });

  it('shows only the bank debits when the money-out tile sends the user here', async () => {
    m.listReconNeedsReview.mockResolvedValue([]);
    m.listRecon.mockResolvedValue([credit, debit]);
    wrap(<BankReconPage />, '/payments/reconciliation?direction=debit&via=money');
    expect(await screen.findByText('CHQ OUT')).toBeTruthy();
    expect(screen.queryByText('NEFT IN')).toBeNull();
    expect(screen.getByText('Opened from Money: Bank debits not matched')).toBeTruthy();
  });

  it('shows every line again on request', async () => {
    m.listReconNeedsReview.mockResolvedValue([]);
    m.listRecon.mockResolvedValue([credit, debit]);
    wrap(<BankReconPage />, '/payments/reconciliation?direction=debit&via=money');
    await screen.findByText('CHQ OUT');
    await userEvent.click(screen.getByRole('button', { name: 'Show everything' }));
    expect(await screen.findByText('NEFT IN')).toBeTruthy();
    expect(screen.getByText('CHQ OUT')).toBeTruthy();
  });

  it('says when the queue is cut off at 100 lines, so a tile with a bigger count is not a mystery', async () => {
    m.listReconNeedsReview.mockResolvedValue([]);
    m.listRecon.mockResolvedValue(
      Array.from({ length: 100 }, (_, i) => ({
        line: { id: 1000 + i, txnDate: '2026-10-03', amount: '10.00', narration: `LINE ${i}`, matchStatus: 'UNMATCHED' },
        suggestions: [],
      })),
    );
    wrap(<BankReconPage />);
    expect(await screen.findByText('Showing the oldest 100 lines. Match some to see the rest.')).toBeTruthy();
  });

  it('does not show the cut-off note for a short queue', async () => {
    m.listReconNeedsReview.mockResolvedValue([]);
    m.listRecon.mockResolvedValue([credit]);
    wrap(<BankReconPage />);
    await screen.findByText('NEFT IN');
    expect(screen.queryByText(/Showing the oldest/)).toBeNull();
  });
});
