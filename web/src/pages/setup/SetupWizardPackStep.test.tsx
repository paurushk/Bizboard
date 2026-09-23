import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { SetupWizardPage } from '@/pages/setup/SetupWizardPage';

const confirmPack = vi.fn();

vi.mock('@/config/features', () => ({ isSetupWizardEnabled: () => true }));
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
vi.mock('@/config/featureFlags', () => ({
  useFeatureFlagEpoch: () => 1,
  isRuntimeFlagEnabled: (key: string) => key === 'ENABLE_ARCHETYPE_PACKS',
  fetchFeatureFlags: vi.fn(),
}));
vi.mock('@/api/osPlan', () => ({
  proposePack: vi.fn(),
  confirmPack: (...args: unknown[]) => confirmPack(...args),
}));
vi.mock('@/api/resources', () => ({
  getCompany: vi.fn().mockResolvedValue({
    id: 9,
    name: 'Funnel Mart',
    registrationType: 'REGULAR',
    gstin: '29AAAAA0000A1Z5',
    state: 'Karnataka',
    address: '12 Shop Street',
    city: 'Bengaluru',
    pincode: '560001',
    bankAccount: '',
    upiId: '',
    onboarding: { started: true, uiStep: 'pack', step: 'pack' },
  }),
  listProducts: vi.fn().mockResolvedValue([{ id: 1, name: 'Soap' }]),
  listCustomers: vi.fn().mockResolvedValue([]),
  updateCompany: vi.fn().mockResolvedValue({}),
  createProduct: vi.fn(),
  createOpeningStock: vi.fn(),
  createCustomer: vi.fn(),
  createSalesInvoice: vi.fn(),
  completeSalesInvoice: vi.fn(),
}));

describe('Setup wizard pack step', () => {
  it('can continue without applying a pack', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/setup?step=pack']}>
          <SetupWizardPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByText('Step 5 of 6')).toBeInTheDocument();
    await userEvent.click(await screen.findByRole('button', { name: 'Continue without a pack' }));
    expect(confirmPack).not.toHaveBeenCalled();
    expect(await screen.findByText('Step 6 of 6')).toBeInTheDocument();
  });
});
