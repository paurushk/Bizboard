import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { BankReconPage, PaymentGatewayPage } from '@/pages/phase/BankingPhasePages';

const m = vi.hoisted(() => ({
  getGatewaySettings: vi.fn(),
  updateGatewaySettings: vi.fn(async (..._args: unknown[]) => ({})),
  getPaymentHealth: vi.fn(async () => ({ unmatchedAging: {}, alerts: [] })),
  listRecon: vi.fn(),
  listReconNeedsReview: vi.fn(),
  matchReconReturn: vi.fn(async (..._args: unknown[]) => ({})),
}));

vi.mock('@/api/resources', () => ({
  getGatewaySettings: () => m.getGatewaySettings(),
  updateGatewaySettings: (...args: unknown[]) => m.updateGatewaySettings(...args),
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

describe('Payments settings: Money In rules', () => {
  it('shows the saved rules and saves a change', async () => {
    m.getGatewaySettings.mockResolvedValue({
      provider: 'razorpay', testMode: true, credentialsConfigured: false,
      chequeAllocationOnClearance: false, cash269stMode: 'warn', advanceGstTreatment: 'none', advanceGstDefaultRate: null,
    });
    wrap(<PaymentGatewayPage />);
    const hold = await screen.findByRole('checkbox', { name: /hold cheques as advances until they clear/i });
    expect((hold as HTMLInputElement).checked).toBe(false);
    expect(screen.getByLabelText(/cash limit check/i).textContent).toBe('Warn');
    await userEvent.click(hold);
    await userEvent.click(screen.getByLabelText(/gst on advances/i));
    await userEvent.click(await screen.findByRole('option', { name: /services/i }));
    await userEvent.type(await screen.findByLabelText(/default gst rate on advances/i), '18');
    await userEvent.click(screen.getByRole('button', { name: /save settings/i }));
    await waitFor(() => expect(m.updateGatewaySettings).toHaveBeenCalledTimes(1));
    expect(m.updateGatewaySettings.mock.calls[0][0]).toMatchObject({
      cheque_allocation_on_clearance: true,
      cash_269st_mode: 'warn',
      advance_gst_treatment: 'services',
      advance_gst_default_rate: '18',
    });
  });
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
