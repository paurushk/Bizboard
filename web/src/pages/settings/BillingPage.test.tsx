import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactElement } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { setLocale, t } from '@/i18n';
import { BillingPage } from '@/pages/settings/BillingPage';

const auth = vi.hoisted(() => ({
  user: { id: 1, email: 'owner@x.test', fullName: 'Owner', role: 'OWNER', companyId: 9, company: { name: 'Shop One' } } as Record<string, unknown>,
}));
vi.mock('@/auth/AuthContext', () => ({ useAuth: () => ({ user: auth.user }) }));

const billing = vi.hoisted(() => ({
  getBillingPortal: vi.fn(),
  listBillingDeadLetters: vi.fn(),
  replayBillingDeadLetter: vi.fn(),
  startBillingCheckout: vi.fn(),
  // WP-BL1/BL2 panel: no Bizboard invoices or TDS claims in these tests.
  listPlatformInvoices: vi.fn(async () => []),
  getTdsClaims: vi.fn(async () => ({ claims: [], sections: [] })),
  submitTdsClaim: vi.fn(),
  refundTdsClaim: vi.fn(),
  // D-19 referral panel: the flag is off in these tests, so it is never called.
  getReferralPanel: vi.fn(),
}));
vi.mock('@/api/billing', () => billing);

const roadmap = vi.hoisted(() => ({
  billingOps: vi.fn(),
  listVendorTenants: vi.fn(),
  suspendSubscription: vi.fn(),
}));
vi.mock('@/api/roadmap', () => roadmap);

const PLAN = { id: 1, name: 'Starter', slug: 'starter', seatLimit: 3, modules: {}, pricePaise: 49900 };
const PORTAL = {
  seatLimit: 3,
  subscription: {
    id: 1,
    status: 'active',
    writeBlocked: false,
    trialEndsAt: null,
    currentPeriodEnd: '2099-11-01',
    plan: PLAN,
  },
  plans: [PLAN, { id: 2, name: 'Growth', slug: 'growth', seatLimit: 10, modules: {}, pricePaise: 99900 }],
};

function wrap(ui: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

async function openDialog() {
  await userEvent.click(await screen.findByRole('button', { name: t('billingDanger.zoneTitle') }));
  await userEvent.click(await screen.findByRole('button', { name: t('billingDanger.open') }));
  return screen.findByRole('dialog');
}

describe('BillingPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    auth.user = { id: 1, email: 'owner@x.test', fullName: 'Owner', role: 'OWNER', companyId: 9, company: { name: 'Shop One' } };
    billing.getBillingPortal.mockResolvedValue(PORTAL);
    billing.startBillingCheckout.mockResolvedValue({ checkoutUrl: null });
    roadmap.billingOps.mockResolvedValue({});
    roadmap.listVendorTenants.mockResolvedValue([]);
    roadmap.suspendSubscription.mockResolvedValue({});
  });
  afterEach(() => setLocale('en'));

  it('renders blocked writes, plan actions and notices from the Hindi catalog', async () => {
    setLocale('hi');
    billing.getBillingPortal.mockResolvedValue({
      ...PORTAL,
      subscription: { ...PORTAL.subscription, status: 'trial', writeBlocked: true, trialEndsAt: '2026-10-20', currentPeriodEnd: '2026-11-01' },
    });
    roadmap.billingOps.mockResolvedValue({
      upgradePrompt: { show: true, reason: 'seats' },
      trialNotice: { show: true, daysLeft: 4 },
    });
    wrap(<BillingPage />);
    expect(await screen.findByText(t('cog.writesBlockedBilling'))).toBeTruthy();
    expect(screen.getAllByText(t('cog.billingSeats', { count: 3 }), { exact: false }).length).toBeGreaterThan(0);
    expect(screen.getAllByText(t('cog.trialEndsAt', { date: '2026-10-20' }), { exact: false }).length).toBeGreaterThan(0);
    expect(screen.getAllByText(t('cog.periodEnds', { date: '2026-11-01' }), { exact: false }).length).toBeGreaterThan(0);
    expect(screen.getByText(t('cog.planLimitReached', { reason: 'seats' }))).toBeTruthy();
    expect(screen.getByText(t('cog.trialDaysLeft', { days: '4' }))).toBeTruthy();
    expect(screen.getByRole('button', { name: t('cog.currentPlan') })).toBeDisabled();
    await userEvent.click(screen.getByRole('button', { name: t('cog.startCheckout') }));
    expect(billing.startBillingCheckout).toHaveBeenCalledWith(2);
  });

  it('has no parked billing events or replay: that is operator work in the admin', async () => {
    wrap(<BillingPage />);
    await screen.findByText(t('sweep2.availablePlans'));
    expect(billing.listBillingDeadLetters).not.toHaveBeenCalled();
    expect(screen.queryByText(t('sweep2.parkedBillingEvents'))).toBeNull();
    expect(screen.queryByRole('button', { name: t('sweep2.replay') })).toBeNull();
  });

  it('shows your tenants only when there are some', async () => {
    wrap(<BillingPage />);
    await screen.findByText(t('sweep2.availablePlans'));
    expect(screen.queryByText(t('billingDanger.tenants'))).toBeNull();
  });

  it('lists the tenants of a vendor company', async () => {
    roadmap.listVendorTenants.mockResolvedValue([
      { sourceCompanyId: 2, sourceCompanyName: 'Shop Two', setupCompletedAt: null, firstInvoiceAt: null },
    ]);
    wrap(<BillingPage />);
    expect(await screen.findByText(t('billingDanger.tenants'))).toBeTruthy();
    expect(
      screen.getByText(t('cog.vendorTenantLine', { name: 'Shop Two', setup: t('cog.setupOpen'), invoice: t('cog.invoiceNo') })),
    ).toBeTruthy();
  });

  it('keeps suspend inside a collapsed danger zone, apart from the plan actions', async () => {
    wrap(<BillingPage />);
    await screen.findByText(t('sweep2.availablePlans'));
    expect(screen.queryByRole('button', { name: t('sweep2.suspend') })).toBeNull();
    expect(screen.getByRole('button', { name: t('billingDanger.zoneTitle') }).getAttribute('aria-expanded')).toBe('false');
  });

  it('asks for a reason, the typed company name and the password before suspending', async () => {
    wrap(<BillingPage />);
    const dialog = await openDialog();
    expect(within(dialog).getByText(t('billingDanger.effectUntil', { date: '2099-11-01' }))).toBeTruthy();
    const go = within(dialog).getByRole('button', { name: t('billingDanger.confirm') }) as HTMLButtonElement;
    expect(go.disabled).toBe(true);
    await userEvent.type(within(dialog).getByLabelText(new RegExp(t('sweep.churnReason'))), 'Closing the shop');
    expect(go.disabled).toBe(true);
    await userEvent.type(within(dialog).getByLabelText(new RegExp('Shop One')), 'shop');
    await userEvent.type(within(dialog).getByLabelText(t('billingDanger.password')), 'pw');
    expect(go.disabled).toBe(true); // name not fully typed
    await userEvent.type(within(dialog).getByLabelText(new RegExp('Shop One')), ' one');
    expect(go.disabled).toBe(false);
    await userEvent.click(go);
    expect(roadmap.suspendSubscription).toHaveBeenCalledWith({
      reason: 'Closing the shop',
      companyName: 'shop one',
      password: 'pw',
      code: '',
    });
  });

  it('sends the two-step code when one is typed', async () => {
    wrap(<BillingPage />);
    const dialog = await openDialog();
    await userEvent.type(within(dialog).getByLabelText(new RegExp(t('sweep.churnReason'))), 'x');
    await userEvent.type(within(dialog).getByLabelText(new RegExp('Shop One')), 'Shop One');
    await userEvent.type(within(dialog).getByLabelText(t('billingDanger.password')), 'pw');
    await userEvent.type(within(dialog).getByLabelText(t('billingDanger.code')), '123456');
    await userEvent.click(within(dialog).getByRole('button', { name: t('billingDanger.confirm') }));
    expect(roadmap.suspendSubscription.mock.calls[0][0].code).toBe('123456');
  });

  it('says the workspace goes read-only at once when no paid period is running', async () => {
    billing.getBillingPortal.mockResolvedValue({
      ...PORTAL,
      subscription: { ...PORTAL.subscription, status: 'trial', currentPeriodEnd: null },
    });
    wrap(<BillingPage />);
    const dialog = await openDialog();
    expect(within(dialog).getByText(t('billingDanger.effectNow'))).toBeTruthy();
  });

  it('shows the server reason inside the dialog and keeps it open', async () => {
    roadmap.suspendSubscription.mockRejectedValueOnce(new Error('Incorrect password.'));
    wrap(<BillingPage />);
    const dialog = await openDialog();
    await userEvent.type(within(dialog).getByLabelText(new RegExp(t('sweep.churnReason'))), 'x');
    await userEvent.type(within(dialog).getByLabelText(new RegExp('Shop One')), 'Shop One');
    await userEvent.type(within(dialog).getByLabelText(t('billingDanger.password')), 'wrong');
    await userEvent.click(within(dialog).getByRole('button', { name: t('billingDanger.confirm') }));
    expect(await within(dialog).findByText('Incorrect password.')).toBeTruthy();
    expect(screen.getByRole('dialog')).toBeTruthy();
  });

  it('cannot be confirmed when the company name is not known', async () => {
    auth.user = { ...auth.user, company: undefined };
    wrap(<BillingPage />);
    const dialog = await openDialog();
    expect(within(dialog).getByText(t('billingDanger.noName'))).toBeTruthy();
    await userEvent.type(within(dialog).getByLabelText(new RegExp(t('sweep.churnReason'))), 'x');
    await userEvent.type(within(dialog).getByLabelText(t('billingDanger.password')), 'pw');
    expect((within(dialog).getByRole('button', { name: t('billingDanger.confirm') }) as HTMLButtonElement).disabled).toBe(true);
  });

  it('offers no danger zone once the workspace is suspended', async () => {
    billing.getBillingPortal.mockResolvedValue({
      ...PORTAL,
      subscription: { ...PORTAL.subscription, status: 'suspended' },
    });
    wrap(<BillingPage />);
    await screen.findByText(t('sweep2.availablePlans'));
    expect(screen.queryByRole('button', { name: t('billingDanger.zoneTitle') })).toBeNull();
  });

  it('shows an error with Retry when the plan cannot be loaded', async () => {
    billing.getBillingPortal.mockRejectedValue(new Error('down'));
    wrap(<BillingPage />);
    expect(await screen.findByRole('button', { name: /retry|try again/i })).toBeTruthy();
    expect(screen.queryByText(t('sweep2.availablePlans'))).toBeNull();
  });
});
