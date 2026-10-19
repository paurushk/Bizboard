import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { t } from '@/i18n';
import { SettingsHubPage } from '@/pages/settings/SettingsHubPage';

const auth = vi.hoisted(() => ({ user: { id: 1, role: 'OWNER', companyId: 9, company: {} } as Record<string, unknown> }));
vi.mock('@/auth/AuthContext', () => ({ useAuth: () => ({ user: auth.user }) }));

const api = vi.hoisted(() => ({ getSettingsHealth: vi.fn() }));
vi.mock('@/api/resources', () => api);

const HEALTH = {
  needsAttention: 2,
  items: [
    { id: 'gstin', status: 'ok', path: '/settings/gst' },
    { id: 'bank', status: 'todo', path: '/settings/bank-accounts' },
    { id: 'licences', status: 'warn', path: '/settings/statutory-licences', count: 2, expired: 1, expiring: 0 },
    { id: 'gateway', status: 'ok', path: '/settings/payment-gateway', configured: true },
    { id: 'users', status: 'ok', path: '/settings/users', pending: 0, expired: 0 },
  ],
};

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <SettingsHubPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('SettingsHubPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    auth.user = { id: 1, role: 'OWNER', companyId: 9, company: {} };
    api.getSettingsHealth.mockResolvedValue(HEALTH);
  });

  it('shows the groups with links to their screens', async () => {
    renderPage();
    expect(await screen.findByRole('heading', { name: t('settingsGroups.business') })).toBeTruthy();
    expect(screen.getByRole('heading', { name: t('settingsGroups.documents') })).toBeTruthy();
    const bank = screen.getByRole('link', { name: new RegExp(t('nav.bankAccounts')) });
    expect(bank.getAttribute('href')).toBe('/settings/bank-accounts');
  });

  it('lists what needs attention, each linking to its screen', async () => {
    renderPage();
    expect(await screen.findByText(t('settingsHub.needsAttention', { count: 2 }))).toBeTruthy();
    expect(screen.getByText(t('settingsHub.licencesExpired', { count: 1 }))).toBeTruthy();
    const link = screen.getByRole('link', { name: new RegExp(t('settingsHub.itemTitle.bank')) });
    expect(link.getAttribute('href')).toBe('/settings/bank-accounts');
  });

  it('shows an error with Retry when the checklist cannot load, and still shows the groups', async () => {
    api.getSettingsHealth.mockRejectedValue(new Error('down'));
    renderPage();
    expect(await screen.findByRole('button', { name: /retry|try again/i })).toBeTruthy();
    expect(screen.getByRole('heading', { name: t('settingsGroups.business') })).toBeTruthy();
  });

  it('hides the checklist and owner-only screens from someone who is not an owner', async () => {
    auth.user = { id: 2, role: 'MANAGER', companyId: 9, canImport: true, canExport: true, company: {} };
    renderPage();
    expect(await screen.findByRole('heading', { name: t('settingsGroups.people') })).toBeTruthy();
    expect(api.getSettingsHealth).not.toHaveBeenCalled();
    expect(screen.queryByRole('link', { name: new RegExp(t('nav.bankAccounts')) })).toBeNull();
  });
});
