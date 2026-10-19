import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { SettingsContinuity } from '@/components/settings/SettingsContinuity';
import { t } from '@/i18n';
import { announceWrite } from '@/utils/settingsSaveSignal';

const auth = vi.hoisted(() => ({ user: { id: 1, role: 'OWNER', companyId: 9, company: {} } as Record<string, unknown> }));
vi.mock('@/auth/AuthContext', () => ({ useAuth: () => ({ user: auth.user }) }));
vi.mock('@/api/resources', () => ({ getSettingsHistory: vi.fn() }));
vi.mock('@/config/featureFlags', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/config/featureFlags')>();
  return { ...actual, isRuntimeFlagEnabled: () => false };
});

function renderAt(path: string) {
  window.history.pushState({}, '', path);
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={[path]}>
        <SettingsContinuity />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('SettingsContinuity (SET-19)', () => {
  beforeEach(() => {
    auth.user = { id: 1, role: 'OWNER', companyId: 9, company: {} };
  });

  it('offers a way back to the overview on a settings screen', () => {
    renderAt('/settings/units');
    expect(screen.getByRole('link', { name: t('settingsContinuity.back') }).getAttribute('href')).toBe('/settings');
  });

  it('offers Recent changes to an owner on a screen with history, and not to others', () => {
    renderAt('/settings/units');
    expect(screen.getByRole('button', { name: t('settingsHistory.open') })).toBeTruthy();
  });

  it('shows where the setting is used, from the impact registry', () => {
    renderAt('/settings/series');
    expect(screen.getByText(t('settingsShell.usedBy'))).toBeTruthy();
    expect(screen.getAllByText(t('nav.sales')).length).toBeGreaterThan(0);
    expect(screen.getByText(t('impact.printedDocuments'))).toBeTruthy();
  });

  it('shows nothing on the overview itself or outside settings', () => {
    const { container } = renderAt('/settings');
    expect(container.textContent).toBe('');
  });

  it('after a save, offers the next screen in set-up order', async () => {
    renderAt('/settings/company');
    expect(screen.queryByRole('alert')).toBeNull();
    act(() => announceWrite('PATCH', '/company/'));
    const next = await screen.findByRole('link', { name: t('settingsContinuity.goNext', { name: t('nav.gst') }) });
    expect(next.getAttribute('href')).toBe('/settings/gst');
    await userEvent.click(screen.getByRole('button', { name: t('common.close') }));
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('does not treat a preview, a check or a read as a save', () => {
    renderAt('/settings/company');
    act(() => {
      announceWrite('GET', '/company/');
      announceWrite('POST', '/payments/gateway-settings/verify/');
      announceWrite('POST', '/company/packs/preview/');
    });
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('skips a next screen the person cannot open, and says "saved" when nothing follows', async () => {
    auth.user = { id: 2, role: 'MANAGER', companyId: 9, canImport: true, canExport: true, company: {} };
    renderAt('/settings/backup');
    act(() => announceWrite('POST', '/company/export/'));
    expect(await screen.findByText(t('settingsContinuity.saved'))).toBeTruthy();
    expect(screen.getByRole('link', { name: t('settingsContinuity.backToOverview') }).getAttribute('href')).toBe('/settings');
  });
});
