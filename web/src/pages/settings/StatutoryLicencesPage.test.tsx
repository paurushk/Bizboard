import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { t } from '@/i18n';
import { StatutoryLicencesPage } from '@/pages/settings/StatutoryLicencesPage';

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 1, email: 'owner@x.test', fullName: 'Owner', role: 'OWNER', companyId: 9 },
  }),
}));
vi.mock('@/hooks/useSubscriptionGate', () => ({ useSubscriptionGate: () => ({ writesBlocked: false }) }));

const api = vi.hoisted(() => ({
  listCompanyStatutoryLicences: vi.fn(),
  getStatutoryLicenceStatus: vi.fn(),
  createCompanyStatutoryLicence: vi.fn(),
  updateCompanyStatutoryLicence: vi.fn(),
  replaceCompanyStatutoryLicence: vi.fn(),
}));
vi.mock('@/api/resources', () => api);

const LOCKED = {
  id: 1,
  licenceType: 'FSSAI',
  licenceNumber: '12345678901234',
  premisesState: 'Maharashtra',
  validUpto: '2030-01-01',
  isActive: true,
  isLocked: true,
};
const FREE = { ...LOCKED, id: 2, licenceNumber: '98765432109876', isLocked: false };

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <StatutoryLicencesPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('StatutoryLicencesPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.listCompanyStatutoryLicences.mockResolvedValue([LOCKED, FREE]);
    api.getStatutoryLicenceStatus.mockResolvedValue({
      enforcement: false,
      regulatedProducts: 3,
      activeLicences: 2,
      expired: 1,
      expiringSoon: 0,
    });
  });

  it('says when the invoice check is off and licences have expired', async () => {
    renderPage();
    expect(await screen.findByText(t('licences.enforcementOffRegulated', { count: '3' }))).toBeTruthy();
    expect(screen.getByText(t('licences.expired', { count: '1' }))).toBeTruthy();
  });

  it('says when the invoice check is on', async () => {
    api.getStatutoryLicenceStatus.mockResolvedValue({
      enforcement: true,
      regulatedProducts: 3,
      activeLicences: 2,
      expired: 0,
      expiringSoon: 0,
    });
    renderPage();
    expect(await screen.findByText(t('licences.enforcementOn'))).toBeTruthy();
  });

  it('still shows the licences when the status call fails', async () => {
    api.getStatutoryLicenceStatus.mockRejectedValue(new Error('down'));
    renderPage();
    expect(await screen.findByText('12345678901234')).toBeTruthy();
    expect(await screen.findByText(t('licences.statusUnavailable'))).toBeTruthy();
  });

  it('offers Renew / replace, not Edit, on a licence that is on issued invoices', async () => {
    renderPage();
    const lockedRow = (await screen.findByText('12345678901234')).closest('tr') as HTMLElement;
    expect(within(lockedRow).getByText(t('licences.locked'))).toBeTruthy();
    expect(within(lockedRow).queryByRole('button', { name: t('common.edit') })).toBeNull();
    expect(within(lockedRow).getByRole('button', { name: t('licences.replace') })).toBeTruthy();
  });

  it('keeps Edit for a licence that is not yet on any invoice', async () => {
    renderPage();
    const freeRow = (await screen.findByText('98765432109876')).closest('tr') as HTMLElement;
    expect(within(freeRow).getByRole('button', { name: t('common.edit') })).toBeTruthy();
    expect(within(freeRow).queryByText(t('licences.locked'))).toBeNull();
  });

  it('renews with the same number: the dialog starts from the current number', async () => {
    api.replaceCompanyStatutoryLicence.mockResolvedValue({});
    renderPage();
    const lockedRow = (await screen.findByText('12345678901234')).closest('tr') as HTMLElement;
    await userEvent.click(within(lockedRow).getByRole('button', { name: t('licences.replace') }));
    expect((screen.getByLabelText(t('licences.newNumber')) as HTMLInputElement).value).toBe('12345678901234');
    await userEvent.type(screen.getByLabelText(t('phase.licenceValidUpto')), '2032-01-01');
    await userEvent.click(screen.getAllByRole('button', { name: t('licences.replace') }).pop() as HTMLElement);
    expect(api.replaceCompanyStatutoryLicence).toHaveBeenCalledWith(1, {
      licence_number: '12345678901234',
      valid_from: null,
      valid_upto: '2032-01-01',
    });
  });

  it('replaces a licence with a new number', async () => {
    api.replaceCompanyStatutoryLicence.mockResolvedValue({});
    renderPage();
    const lockedRow = (await screen.findByText('12345678901234')).closest('tr') as HTMLElement;
    await userEvent.click(within(lockedRow).getByRole('button', { name: t('licences.replace') }));
    const number = screen.getByLabelText(t('licences.newNumber'));
    await userEvent.clear(number);
    await userEvent.type(number, '11112222333344');
    await userEvent.click(screen.getAllByRole('button', { name: t('licences.replace') }).pop() as HTMLElement);
    expect(api.replaceCompanyStatutoryLicence).toHaveBeenCalledWith(1, {
      licence_number: '11112222333344',
      valid_from: null,
      valid_upto: null,
    });
  });
});
