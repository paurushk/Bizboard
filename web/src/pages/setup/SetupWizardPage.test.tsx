import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { setLocale, t } from '@/i18n';
import { SetupWizardPage } from '@/pages/setup/SetupWizardPage';
import { trackJourneyFailed, trackJourneyStarted } from '@/lib/telemetry';

vi.mock('@/config/features', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/config/features')>();
  return { ...actual, isSetupWizardEnabled: () => true };
});

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 1, email: 'owner@x.test', fullName: 'Owner', role: 'OWNER', companyId: 9 },
  }),
}));

vi.mock('@/pages/help/PreventionNote', () => ({ PreventionNote: () => null }));
vi.mock('@/onboarding/analytics', () => ({ trackOnboardingEvent: vi.fn() }));

vi.mock('@/lib/telemetry', () => ({
  trackJourneyStarted: vi.fn(),
  trackJourneyFailed: vi.fn(),
  classifyCompleteFailure: vi.fn(() => 'validation'),
}));

vi.mock('@/api/resources', () => ({
  getCompany: vi.fn().mockResolvedValue({
    id: 9,
    name: 'Funnel Mart',
    registrationType: 'REGULAR',
    gstin: '',
    state: 'Karnataka',
    address: '',
    city: '',
    pincode: '',
    bankAccount: '',
    upiId: '',
    onboarding: { started: true, uiStep: 'tax', step: 'tax' },
  }),
  listProducts: vi.fn().mockResolvedValue([]),
  listCustomers: vi.fn().mockResolvedValue([]),
  updateCompany: vi.fn().mockResolvedValue({}),
  createProduct: vi.fn(),
  createOpeningStock: vi.fn(),
  createCustomer: vi.fn().mockResolvedValue({ id: 1, name: 'Walk-in Customer' }),
  createSalesInvoice: vi.fn(),
  completeSalesInvoice: vi.fn(),
}));

function wrap(initialEntries = ['/setup']) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={initialEntries}>
        <SetupWizardPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('SetupWizard tax journey', () => {
  it('emits signup started + validation failed when Regular GSTIN is empty', async () => {
    wrap();
    await screen.findByLabelText(/GSTIN/i);
    const save = await waitFor(() => {
      const buttons = screen.getAllByRole('button', { name: /save & continue/i });
      const enabled = buttons.find((b) => !(b as HTMLButtonElement).disabled);
      if (!enabled) throw new Error('save still disabled');
      return enabled;
    });
    await userEvent.click(save);
    expect(trackJourneyStarted).toHaveBeenCalledWith('signup');
    expect(trackJourneyFailed).toHaveBeenCalledWith('signup', 'validation');
    expect(await screen.findByText(/GSTIN is required/i)).toBeInTheDocument();
  }, 15_000);

  it('saves first bill as draft and does not complete sales invoice (CW-PR-3)', async () => {
    const { listProducts, createSalesInvoice, completeSalesInvoice } = await import('@/api/resources');
    vi.mocked(listProducts).mockResolvedValue([
      { id: 1, name: 'Sample Item', sellingPrice: 100, gstRate: 18 } as unknown as import('@/types/domain').Product,
    ]);
    vi.mocked(createSalesInvoice).mockResolvedValue({ id: 101 } as unknown as import('@/types/domain').SalesInvoice);
    wrap(['/setup?step=first_bill']);
    const createBtn = (await screen.findAllByRole('button', { name: /create first bill/i }))[0];
    await userEvent.click(createBtn);
    await waitFor(() => expect(createSalesInvoice).toHaveBeenCalled());
    expect(completeSalesInvoice).not.toHaveBeenCalled();
    expect(await screen.findByRole('link', { name: /review & finalize bill/i })).toHaveAttribute(
      'href',
      '/sales/history/101/edit',
    );
  });
});

describe('SetupWizard choosing the step', () => {
  afterEach(() => setLocale('en'));
  const company = (extra: Record<string, unknown> = {}) => ({
    id: 9,
    name: 'Funnel Mart',
    registrationType: 'REGULAR',
    gstin: '29ABCDE1234F1Z5',
    state: 'Karnataka',
    address: '12 MG Road',
    city: 'Bengaluru',
    pincode: '560001',
    bankAccount: '123456',
    upiId: 'shop@upi',
    onboarding: { started: true, uiStep: 'tax', step: 'tax' },
    ...extra,
  });

  async function useCompany(value: Record<string, unknown>) {
    const { getCompany } = await import('@/api/resources');
    vi.mocked(getCompany).mockResolvedValue(value as unknown as import('@/types/domain').Company);
  }

  it('shows the saved company details in the form', async () => {
    await useCompany(company({ onboarding: { started: true, uiStep: 'shop', step: 'shop' } }));
    wrap(['/setup']);
    expect(await screen.findByDisplayValue('12 MG Road')).toBeInTheDocument();
    expect(screen.getByDisplayValue('Bengaluru')).toBeInTheDocument();
    expect(screen.getByDisplayValue('560001')).toBeInTheDocument();
  });

  it('resumes at the step the owner reached last time', async () => {
    await useCompany(company({ onboarding: { started: true, uiStep: 'payments', step: 'payments' } }));
    wrap(['/setup']);
    expect(await screen.findByDisplayValue('shop@upi')).toBeInTheDocument();
  });

  it('opens the step named in the address instead of the saved one', async () => {
    await useCompany(company({ onboarding: { started: true, uiStep: 'tax', step: 'tax' } }));
    wrap(['/setup?step=payments']);
    expect(await screen.findByDisplayValue('shop@upi')).toBeInTheDocument();
  });

  it('starts on the tax step when there is no saved step and no step in the address', async () => {
    await useCompany(company({ onboarding: { started: true } }));
    wrap(['/setup']);
    expect(await screen.findByLabelText(/GSTIN/i)).toBeInTheDocument();
  });

  it('ignores a step name it does not know', async () => {
    await useCompany(company({ onboarding: { started: true } }));
    wrap(['/setup?step=nonsense']);
    expect(await screen.findByLabelText(/GSTIN/i)).toBeInTheDocument();
  });

  it('stores Hindi sample names and reuses a walk-in customer in the active language', async () => {
    setLocale('hi');
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    const { createProduct, listProducts, listCustomers, createCustomer, createSalesInvoice } = await import('@/api/resources');
    vi.mocked(createProduct).mockResolvedValue({ id: 8 } as never);
    vi.mocked(listProducts).mockResolvedValue([
      { id: 1, name: 'Existing', sellingPrice: 100, gstRate: 18 } as never,
    ]);
    vi.mocked(listCustomers).mockResolvedValue([]);
    vi.mocked(createCustomer).mockResolvedValue({ id: 3, name: t('cog.sampleWalkIn') } as never);
    vi.mocked(createSalesInvoice).mockResolvedValue({ id: 101 } as never);

    const catalog = wrap(['/setup?step=catalog']);
    await userEvent.click(await screen.findByRole('button', { name: t('setup.addSamples') }));
    await waitFor(() => expect(createProduct).toHaveBeenCalledTimes(3));
    expect(createProduct).toHaveBeenCalledWith(expect.objectContaining({
      name: t('cog.sampleItem'),
      sku: 'SAMPLE-ITEM',
      description: t('cog.sampleDataNote'),
    }));
    expect(createProduct).toHaveBeenCalledWith(expect.objectContaining({
      name: t('cog.sampleService'),
      sku: 'SAMPLE-SERVICE',
    }));
    expect(createProduct).toHaveBeenCalledWith(expect.objectContaining({
      name: t('cog.deliveryCharge'),
      sku: 'SAMPLE-DELIVERY',
    }));
    expect(confirmSpy).toHaveBeenCalledWith(t('setup.addSamplesConfirm'));

    catalog.unmount();
    vi.mocked(createCustomer).mockClear();
    vi.mocked(listCustomers).mockResolvedValue([
      { id: 4, name: 'Walk-in Customer', state: 'Karnataka', status: 'ACTIVE' } as never,
    ]);
    const reused = wrap(['/setup?step=first_bill']);
    await userEvent.click((await screen.findAllByRole('button', { name: t('setup.createFirstBill') }))[0]);
    await waitFor(() => expect(createSalesInvoice).toHaveBeenCalled());
    expect(createCustomer).not.toHaveBeenCalled();

    reused.unmount();
    vi.mocked(createSalesInvoice).mockClear();
    vi.mocked(listCustomers).mockResolvedValue([]);
    wrap(['/setup?step=first_bill']);
    await userEvent.click((await screen.findAllByRole('button', { name: t('setup.createFirstBill') }))[0]);
    await waitFor(() => expect(createCustomer).toHaveBeenCalledWith({
      name: t('cog.sampleWalkIn'),
      state: 'Karnataka',
      status: 'ACTIVE',
    }));
    confirmSpy.mockRestore();
  });

  it('marks onboarding as started once, the first time the company loads', async () => {
    const { updateCompany } = await import('@/api/resources');
    vi.mocked(updateCompany).mockClear();
    await useCompany(company({ onboarding: { started: false } }));
    wrap(['/setup']);
    await waitFor(() => expect(updateCompany).toHaveBeenCalledWith({ markOnboardingStarted: true }));
    expect(vi.mocked(updateCompany).mock.calls.filter((c) => (c[0] as { markOnboardingStarted?: boolean }).markOnboardingStarted)).toHaveLength(1);
  });
});
