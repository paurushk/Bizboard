import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
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
  createCustomer: vi.fn(),
  createSalesInvoice: vi.fn(),
  completeSalesInvoice: vi.fn(),
}));

function wrap() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
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
});
