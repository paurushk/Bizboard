import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactElement } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { setLocale, t } from '@/i18n';
import { BillingPage } from '@/pages/settings/BillingPage';

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 1, email: 'owner@x.test', fullName: 'Owner', role: 'OWNER', companyId: 9 },
  }),
}));

vi.mock('@/api/billing', () => ({
  getBillingPortal: vi.fn(),
  listBillingDeadLetters: vi.fn(),
  replayBillingDeadLetter: vi.fn(),
  startBillingCheckout: vi.fn(),
}));

vi.mock('@/api/resources', () => ({
  getGatewaySettings: vi.fn(),
}));

vi.mock('@/api/roadmap', () => ({
  billingOps: vi.fn(),
  listVendorTenants: vi.fn(),
  suspendSubscription: vi.fn(),
}));

function wrap(ui: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('BillingPage Hindi copy', () => {
  afterEach(() => setLocale('en'));

  it('renders blocked writes, plan actions, and confirmations from the Hindi catalog', async () => {
    setLocale('hi');
    const { getBillingPortal, listBillingDeadLetters, startBillingCheckout } = await import('@/api/billing');
    const { getGatewaySettings } = await import('@/api/resources');
    const { billingOps, listVendorTenants, suspendSubscription } = await import('@/api/roadmap');
    vi.mocked(getBillingPortal).mockResolvedValue({
      seatLimit: 3,
      subscription: {
        id: 1,
        status: 'trial',
        writeBlocked: true,
        trialEndsAt: '2026-10-20',
        currentPeriodEnd: '2026-11-01',
        plan: { id: 1, name: 'Starter', slug: 'starter', seatLimit: 3, modules: {}, pricePaise: 49900 },
      },
      plans: [
        { id: 1, name: 'Starter', slug: 'starter', seatLimit: 3, modules: {}, pricePaise: 49900 },
        { id: 2, name: 'Growth', slug: 'growth', seatLimit: 10, modules: {}, pricePaise: 99900 },
      ],
    });
    vi.mocked(getGatewaySettings).mockResolvedValue({ credentialsConfigured: true } as never);
    vi.mocked(billingOps).mockResolvedValue({
      upgradePrompt: { show: true, reason: 'seats' },
      trialNotice: { show: true, daysLeft: 4 },
    });
    vi.mocked(listVendorTenants).mockResolvedValue([
      { sourceCompanyId: 2, sourceCompanyName: 'Shop Two', setupCompletedAt: null, firstInvoiceAt: null },
    ] as never);
    vi.mocked(listBillingDeadLetters).mockResolvedValue([
      { id: 9, provider: 'razorpay', status: 'pending', error: 'timeout', eventId: 'evt_1' },
    ] as never);
    vi.mocked(startBillingCheckout).mockResolvedValue({ checkoutUrl: null } as never);
    vi.mocked(suspendSubscription).mockResolvedValue({});
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);

    wrap(<BillingPage />);

    expect(await screen.findByText(t('cog.writesBlockedBilling'))).toBeTruthy();
    expect(screen.getAllByText(t('cog.billingSeats', { count: 3 }), { exact: false }).length).toBeGreaterThan(0);
    expect(screen.getAllByText(t('cog.trialEndsAt', { date: '2026-10-20' }), { exact: false }).length).toBeGreaterThan(0);
    expect(screen.getAllByText(t('cog.periodEnds', { date: '2026-11-01' }), { exact: false }).length).toBeGreaterThan(0);
    expect(screen.getByText(t('cog.planLimitReached', { reason: 'seats' }))).toBeTruthy();
    expect(screen.getByText(t('cog.trialDaysLeft', { days: '4' }))).toBeTruthy();
    expect(screen.getByText(t('cog.vendorTenantLine', {
      name: 'Shop Two',
      setup: t('cog.setupOpen'),
      invoice: t('cog.invoiceNo'),
    }))).toBeTruthy();
    expect(screen.getAllByText(t('cog.perMonth'), { exact: false }).length).toBeGreaterThan(0);
    expect(screen.getByRole('button', { name: t('cog.currentPlan') })).toBeDisabled();
    expect(screen.getByText(t('cog.parkedBillingHelp'))).toBeTruthy();

    await userEvent.click(screen.getByRole('button', { name: t('cog.startCheckout') }));
    expect(startBillingCheckout).toHaveBeenCalledWith(2);

    await userEvent.type(screen.getByLabelText(t('sweep.churnReason')), 'closing');
    await userEvent.click(screen.getByRole('button', { name: t('sweep2.suspend') }));
    expect(confirmSpy).toHaveBeenCalledWith(t('cog.suspendWorkspace'));
    expect(suspendSubscription).toHaveBeenCalledWith('closing');
    confirmSpy.mockRestore();
  });
});
