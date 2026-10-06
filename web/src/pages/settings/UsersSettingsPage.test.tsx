import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactElement } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { setLocale, t } from '@/i18n';
import { UsersSettingsPage } from '@/pages/settings/UsersSettingsPage';

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 1, email: 'owner@x.test', fullName: 'Owner', role: 'OWNER', companyId: 9 },
  }),
}));

vi.mock('@/components/TwoStepVerificationPanel', () => ({
  TwoStepVerificationPanel: () => null,
}));

vi.mock('@/api/resources', () => ({
  listCompanyUsers: vi.fn(),
  inviteCompanyUser: vi.fn(),
  updateCompanyUser: vi.fn(),
}));

function wrap(ui: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

const staff = {
  id: 4,
  fullName: 'Ravi',
  email: 'ravi@x.test',
  role: 'SALES_STAFF',
  isActive: true,
  canCreateSales: true,
  canCreatePurchases: false,
  canCreatePayments: false,
  canManageInventory: false,
  canImport: false,
  canCancelDocuments: false,
  canViewFinancialReports: false,
  canExport: false,
};

describe('UsersSettingsPage Hindi confirmations', () => {
  afterEach(() => setLocale('en'));

  it('asks in Hindi before granting export, and skips the update when declined', async () => {
    setLocale('hi');
    const { listCompanyUsers, updateCompanyUser } = await import('@/api/resources');
    vi.mocked(listCompanyUsers).mockResolvedValue([staff] as never);
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
    wrap(<UsersSettingsPage />);
    await userEvent.click(await screen.findByRole('checkbox', { name: 'Export: Ravi' }));
    expect(confirmSpy).toHaveBeenCalledWith(t('cog.allowCap', { action: t('cog.capExport') }));
    expect(updateCompanyUser).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });

  it('warns in Hindi when a staff invite has no work permissions', async () => {
    setLocale('hi');
    const { listCompanyUsers, inviteCompanyUser } = await import('@/api/resources');
    vi.mocked(listCompanyUsers).mockResolvedValue([staff] as never);
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
    wrap(<UsersSettingsPage />);
    await screen.findByRole('checkbox', { name: 'Export: Ravi' });
    await userEvent.click(screen.getByRole('button', { name: t('common.invite') }));
    await userEvent.type(screen.getByRole('textbox', { name: t('common.email') }), 'new@x.test');
    await userEvent.click(screen.getByRole('checkbox', { name: t('users.canCreateSales') }));
    await userEvent.click(screen.getByRole('checkbox', { name: t('users.canRecordPayments') }));
    await userEvent.click(screen.getByRole('button', { name: t('common.save') }));
    expect(confirmSpy).toHaveBeenCalledWith(t('cog.noWorkPermissions'));
    expect(inviteCompanyUser).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });
});
