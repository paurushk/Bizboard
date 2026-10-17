import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { PaymentLinksPage } from '@/pages/phase/BankingPhasePages';

const soon = new Date(Date.now() + 86_400_000).toISOString();
const past = new Date(Date.now() - 86_400_000).toISOString();

const LINKS = [
  { id: 1, token: 't1', invoiceNumber: 'INV-1', customerName: 'Open Sent', amount: '100.00', status: 'SENT', provider: 'razorpay', expiresAt: soon },
  { id: 2, token: 't2', invoiceNumber: 'INV-2', customerName: 'Already Paid', amount: '200.00', status: 'PAID', provider: 'razorpay', expiresAt: null },
  { id: 3, token: 't3', invoiceNumber: 'INV-3', customerName: 'Gone Stale', amount: '300.00', status: 'SENT', provider: 'razorpay', expiresAt: past },
  { id: 4, token: 't4', invoiceNumber: 'INV-4', customerName: 'Never Expires', amount: '400.00', status: 'CREATED', provider: 'razorpay', expiresAt: null },
];

vi.mock('@/api/resources', () => ({
  listAllPaymentLinks: async () => LINKS,
  listGatewayPaymentsPage: async () => ({ results: [], count: 0, next: null, previous: null }),
  listCustomersPage: async () => ({ results: [], count: 0, next: null, previous: null }),
  listSalesInvoicesPage: async () => ({ results: [], count: 0, next: null, previous: null }),
  createPaymentLink: vi.fn(),
  cancelPaymentLink: vi.fn(),
  sharePaymentLink: vi.fn(),
  listGatewayPayments: vi.fn(),
  refundGatewayPayment: vi.fn(),
  retryGatewayPaymentBooks: vi.fn(),
}));
vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ user: { id: 1, email: 'o@x.test', fullName: 'O', role: 'OWNER', companyId: 9 } }),
}));
vi.mock('@/hooks/useSubscriptionGate', () => ({ useSubscriptionGate: () => ({ writesBlocked: false }) }));

function wrap(path = '/') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <PaymentLinksPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => vi.clearAllMocks());

describe('PaymentLinksPage opened from the Money hub', () => {
  it('shows only links a customer can still pay: sent or created, and not expired', async () => {
    wrap('/payments/links?status=open&via=money');
    expect(await screen.findByText('Open Sent')).toBeTruthy();
    expect(screen.getByText('Never Expires')).toBeTruthy();
    expect(screen.queryByText('Already Paid')).toBeNull();
    expect(screen.queryByText('Gone Stale')).toBeNull();
    expect(screen.getByText('Opened from Money: Payment links still open')).toBeTruthy();
  });

  it('shows every link again on request', async () => {
    wrap('/payments/links?status=open&via=money');
    await screen.findByText('Open Sent');
    await userEvent.click(screen.getByRole('button', { name: 'Show everything' }));
    expect(await screen.findByText('Already Paid')).toBeTruthy();
    expect(screen.getByText('Gone Stale')).toBeTruthy();
  });

  it('opened from the online-payments tile (no status) lists every link and names the slice', async () => {
    wrap('/payments/links?via=money');
    expect(await screen.findByText('Already Paid')).toBeTruthy();
    expect(screen.getByText('Opened from Money: Online payments not yet in your books')).toBeTruthy();
  });

  it('is an ordinary page when opened directly', async () => {
    wrap();
    await screen.findByText('Already Paid');
    await waitFor(() => expect(screen.queryByText(/Opened from Money/)).toBeNull());
  });
});
