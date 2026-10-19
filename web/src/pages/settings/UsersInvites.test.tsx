import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { t } from '@/i18n';
import { UsersSettingsPage } from '@/pages/settings/UsersSettingsPage';

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ user: { id: 1, email: 'owner@x.test', fullName: 'Owner', role: 'OWNER', companyId: 9 } }),
}));
vi.mock('@/components/TwoStepVerificationPanel', () => ({ TwoStepVerificationPanel: () => null }));

const api = vi.hoisted(() => ({
  listCompanyUsers: vi.fn(),
  inviteCompanyUser: vi.fn(),
  updateCompanyUser: vi.fn(),
  resendCompanyUserInvite: vi.fn(),
  revokeCompanyUserInvite: vi.fn(),
}));
vi.mock('@/api/resources', () => api);

const base = {
  role: 'SALES_STAFF',
  canCreateSales: true,
  canCreatePurchases: false,
  canCreatePayments: false,
  canManageInventory: false,
  canImport: false,
  canCancelDocuments: false,
  canViewFinancialReports: false,
  canExport: false,
};
const OWNER = { ...base, id: 1, fullName: 'Owner', email: 'owner@x.test', role: 'OWNER', isActive: true, inviteState: 'accepted', lastLogin: '2026-10-18T09:30:00Z' };
const JOINED = { ...base, id: 2, fullName: 'Ravi', email: 'ravi@x.test', isActive: true, inviteState: 'accepted', lastLogin: null };
const PENDING = { ...base, id: 3, fullName: 'Asha', email: 'asha@x.test', isActive: false, inviteState: 'pending', inviteExpiresAt: '2026-10-25T00:00:00Z', lastLogin: null };
const EXPIRED = { ...base, id: 4, fullName: 'Dev', email: 'dev@x.test', isActive: false, inviteState: 'expired', lastLogin: null };
const SWITCHED_OFF = { ...base, id: 5, fullName: 'Mina', email: 'mina@x.test', isActive: false, inviteState: 'deactivated', lastLogin: '2026-09-01T09:00:00Z' };

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <UsersSettingsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const rowOf = async (text: string) => (await screen.findByText(text)).closest('tr') as HTMLElement;

describe('UsersSettingsPage: sign-in and invites', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.listCompanyUsers.mockResolvedValue([OWNER, JOINED, PENDING, EXPIRED, SWITCHED_OFF]);
    api.resendCompanyUserInvite.mockResolvedValue({ inviteUrl: 'https://app.test/invite?token=abc', inviteExpiresAt: '2026-10-26T00:00:00Z' });
    api.revokeCompanyUserInvite.mockResolvedValue({ revoked: 1 });
    vi.spyOn(window, 'confirm').mockReturnValue(true);
  });

  it('shows when each person last signed in, or never', async () => {
    renderPage();
    expect(within(await rowOf('Ravi')).getByText(t('usersAdmin.never'))).toBeTruthy();
    expect(within(await rowOf('Mina')).queryByText(t('usersAdmin.never'))).toBeNull();
  });

  it('says an unaccepted invite is pending, with its date, or has expired, instead of just "inactive"', async () => {
    renderPage();
    const pending = await rowOf('Asha');
    expect(within(pending).getByText(t('usersAdmin.invitePending', { date: new Date('2026-10-25T00:00:00Z').toLocaleDateString() }))).toBeTruthy();
    expect(within(await rowOf('Dev')).getByText(t('usersAdmin.inviteExpired'))).toBeTruthy();
    expect(within(await rowOf('Mina')).getByText(t('status.INACTIVE'))).toBeTruthy();
  });

  it('offers resend and cancel only for invites that have not been accepted', async () => {
    renderPage();
    for (const name of ['Asha', 'Dev']) {
      const row = await rowOf(name);
      expect(within(row).getByRole('button', { name: t('usersAdmin.resend') })).toBeTruthy();
      expect(within(row).getByRole('button', { name: t('usersAdmin.revoke') })).toBeTruthy();
      // An unaccepted invite is not "reactivated": that button would skip the person's consent.
      expect(within(row).queryByRole('button', { name: t('users.reactivate') })).toBeNull();
    }
    for (const name of ['Ravi', 'Mina', 'Owner']) {
      expect(within(await rowOf(name)).queryByRole('button', { name: t('usersAdmin.resend') })).toBeNull();
    }
    expect(within(await rowOf('Mina')).getByRole('button', { name: t('users.reactivate') })).toBeTruthy();
  });

  it('resends an invite and shows the new link with its expiry to copy', async () => {
    renderPage();
    await userEvent.click(within(await rowOf('Asha')).getByRole('button', { name: t('usersAdmin.resend') }));
    await waitFor(() => expect(api.resendCompanyUserInvite).toHaveBeenCalledWith(3));
    expect(await screen.findByText('https://app.test/invite?token=abc')).toBeTruthy();
    expect(screen.getByRole('button', { name: t('usersAdmin.copy') })).toBeTruthy();
  });

  it('cancels an invite only after confirmation', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValueOnce(false).mockReturnValue(true);
    renderPage();
    const row = await rowOf('Dev');
    await userEvent.click(within(row).getByRole('button', { name: t('usersAdmin.revoke') }));
    expect(api.revokeCompanyUserInvite).not.toHaveBeenCalled();
    await userEvent.click(within(row).getByRole('button', { name: t('usersAdmin.revoke') }));
    await waitFor(() => expect(api.revokeCompanyUserInvite).toHaveBeenCalledWith(4));
    expect(confirm).toHaveBeenCalledTimes(2);
  });

  it('shows the server reason when a resend is refused', async () => {
    api.resendCompanyUserInvite.mockRejectedValueOnce(new Error('This person has already joined.'));
    renderPage();
    await userEvent.click(within(await rowOf('Asha')).getByRole('button', { name: t('usersAdmin.resend') }));
    expect(await screen.findByText(/already joined/)).toBeTruthy();
  });
});
