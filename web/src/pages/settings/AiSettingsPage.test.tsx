import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { t } from '@/i18n';
import { AiSettingsPage } from '@/pages/settings/AiSettingsPage';

vi.mock('@/auth/AuthContext', () => ({ useAuth: () => ({ user: { id: 1, role: 'OWNER', companyId: 9 } }) }));

const api = vi.hoisted(() => ({ getCompany: vi.fn(), updateCompany: vi.fn() }));
vi.mock('@/api/resources', () => api);

const COMPANY = {
  aiFeaturesEnabled: false,
  aiMonthlyTokenBudget: null,
  dailySummaryEmailEnabled: false,
  openingCashBalance: null,
  openingCashAsOf: null,
};

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <AiSettingsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('AiSettingsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getCompany.mockResolvedValue(COMPANY);
    api.updateCompany.mockResolvedValue({});
  });

  it('shows whether bill scan is on or off as a status, not a switch, and says who controls it', async () => {
    renderPage();
    expect(await screen.findByText(t('aiPage.statusOff'))).toBeTruthy();
    expect(screen.getByText(new RegExp(t('aiPage.statusHelp').slice(0, 30)))).toBeTruthy();
    expect(screen.queryByLabelText(t('insights.enableAi'))).toBeNull();
  });

  it('shows the company as on, and the monthly limit', async () => {
    api.getCompany.mockResolvedValue({ ...COMPANY, aiFeaturesEnabled: true, aiMonthlyTokenBudget: 500000 });
    renderPage();
    expect(await screen.findByText(t('aiPage.statusOn'))).toBeTruthy();
    expect(screen.getByText(new RegExp('500000'))).toBeTruthy();
  });

  it('never sends the two settings the server ignores from an owner', async () => {
    renderPage();
    await userEvent.click(await screen.findByLabelText(t('insights.dailyEmail')));
    await userEvent.click(screen.getByRole('button', { name: t('common.save') }));
    await waitFor(() => expect(api.updateCompany).toHaveBeenCalled());
    const payload = api.updateCompany.mock.calls[0][0];
    expect(payload).toEqual({ dailySummaryEmailEnabled: true, openingCashBalance: null, openingCashAsOf: null });
    expect(payload).not.toHaveProperty('aiFeaturesEnabled');
    expect(payload).not.toHaveProperty('aiMonthlyTokenBudget');
  });

  it('wants both an opening cash and its date, or neither', async () => {
    renderPage();
    await userEvent.type(await screen.findByLabelText(t('insights.openingCash')), '5000');
    await userEvent.click(screen.getByRole('button', { name: t('common.save') }));
    expect(await screen.findByText(t('aiPage.cashNeedsBoth'))).toBeTruthy();
    expect(api.updateCompany).not.toHaveBeenCalled();
  });

  it('refuses an opening cash that is not a number', async () => {
    renderPage();
    await userEvent.type(await screen.findByLabelText(t('insights.openingCash')), 'lots');
    await userEvent.type(screen.getByLabelText(t('insights.openingCashAsOf')), '2026-04-01');
    await userEvent.click(screen.getByRole('button', { name: t('common.save') }));
    expect(await screen.findByText(t('aiPage.cashNotNumber'))).toBeTruthy();
    expect(api.updateCompany).not.toHaveBeenCalled();
  });

  it('saves a balance with its date', async () => {
    renderPage();
    await userEvent.type(await screen.findByLabelText(t('insights.openingCash')), '5000');
    await userEvent.type(screen.getByLabelText(t('insights.openingCashAsOf')), '2026-04-01');
    await userEvent.click(screen.getByRole('button', { name: t('common.save') }));
    await waitFor(() => expect(api.updateCompany).toHaveBeenCalled());
    expect(api.updateCompany.mock.calls[0][0]).toMatchObject({ openingCashBalance: '5000', openingCashAsOf: '2026-04-01' });
  });

  it('shows an error with Retry rather than a blank form when the company cannot load', async () => {
    api.getCompany.mockRejectedValue(new Error('down'));
    renderPage();
    expect(await screen.findByRole('button', { name: /retry|try again/i })).toBeTruthy();
    expect(screen.queryByLabelText(t('insights.dailyEmail'))).toBeNull();
  });
});
