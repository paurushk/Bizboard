import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { t } from '@/i18n';
import { CompanySettingsPage } from '@/pages/settings/CompanySettingsPage';

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ user: { id: 1, role: 'OWNER', companyId: 9, company: {} } }),
}));
vi.mock('@/pages/settings/InvoiceBankSummary', () => ({ InvoiceBankSummary: () => <div>bank-summary</div> }));

const api = vi.hoisted(() => ({ getCompany: vi.fn(), updateCompany: vi.fn() }));
vi.mock('@/api/resources', () => api);

const COMPANY = {
  name: 'Sharma Traders',
  legalName: '',
  address: '1 Main Road',
  city: 'Delhi',
  state: 'Delhi',
  pincode: '110001',
  phone: '',
  email: '',
  gstin: '',
  updatedAt: '2026-10-19T10:00:00Z',
};

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <CompanySettingsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('CompanySettingsPage (SET-17)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getCompany.mockResolvedValue(COMPANY);
    api.updateCompany.mockResolvedValue(COMPANY);
  });

  it('shows identity, address and contact only: no reminder or credit hold controls', async () => {
    renderPage();
    expect(await screen.findByLabelText(new RegExp(t('sweep.shopDisplayName')))).toBeTruthy();
    expect(screen.queryByLabelText(t('settings.dunningEnabled'))).toBeNull();
    expect(screen.queryByLabelText(t('settings.autoCreditHold'))).toBeNull();
    expect(screen.getByRole('link', { name: t('nav.moneyInRules') }).getAttribute('href')).toBe('/settings/money-in');
  });

  it('points at GST settings when the GSTIN is not set', async () => {
    renderPage();
    const chip = await screen.findByRole('link', { name: t('companyPage.gstinMissing') });
    expect(chip.getAttribute('href')).toBe('/settings/gst');
  });

  it('saves only the identity fields', async () => {
    renderPage();
    const city = await screen.findByLabelText(t('sweep.city'));
    await userEvent.clear(city);
    await userEvent.type(city, 'Pune');
    await userEvent.click(screen.getByRole('button', { name: t('common.save') }));
    await waitFor(() => expect(api.updateCompany).toHaveBeenCalledTimes(1));
    const sent = api.updateCompany.mock.calls[0][0];
    expect(sent.city).toBe('Pune');
    for (const gone of ['dunningEnabled', 'dunningDays', 'autoCreditHoldOnSevereOverdue', 'bankAccount', 'upiId']) {
      expect(sent).not.toHaveProperty(gone);
    }
  });

  it('sends the time the record was loaded, so a second owner edit is not overwritten', async () => {
    renderPage();
    const city = await screen.findByLabelText(t('sweep.city'));
    await userEvent.type(city, 'x');
    await userEvent.click(screen.getByRole('button', { name: t('common.save') }));
    await waitFor(() => expect(api.updateCompany).toHaveBeenCalledTimes(1));
    expect(api.updateCompany.mock.calls[0][0].expected_updated_at).toBe('2026-10-19T10:00:00Z');
  });

  it('shows the conflict dialog when the server says the record changed', async () => {
    const conflict = Object.assign(new Error('stale'), { isAxiosError: true, response: { status: 409, data: {} } });
    api.updateCompany.mockRejectedValueOnce(conflict);
    renderPage();
    const city = await screen.findByLabelText(t('sweep.city'));
    await userEvent.type(city, 'x');
    await userEvent.click(screen.getByRole('button', { name: t('common.save') }));
    expect(await screen.findByText(t('settingsShell.conflictTitle'))).toBeTruthy();
  });

  it('refuses a bad pincode with a reason', async () => {
    renderPage();
    const pin = await screen.findByLabelText(t('sweep.pinCode'));
    await userEvent.clear(pin);
    await userEvent.type(pin, '12');
    await userEvent.click(screen.getByRole('button', { name: t('common.save') }));
    expect(await screen.findByText(t('validation.pincode'))).toBeTruthy();
    expect(api.updateCompany).not.toHaveBeenCalled();
  });

  it('shows an error with Retry when the company cannot load', async () => {
    api.getCompany.mockRejectedValue(new Error('down'));
    renderPage();
    expect(await screen.findByRole('button', { name: /retry|try again/i })).toBeTruthy();
  });
});
