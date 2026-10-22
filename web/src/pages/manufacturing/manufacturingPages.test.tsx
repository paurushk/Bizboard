import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderRoutes } from '@/test/careHarness';

const state = vi.hoisted(() => ({
  role: 'OWNER',
  recipes: [] as unknown[],
  flags: {} as Record<string, boolean>,
}));

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ user: { id: 1, companyId: 7, role: state.role } }),
}));
vi.mock('@/hooks/useSubscriptionGate', () => ({ useSubscriptionGate: () => ({ writesBlocked: false }) }));
vi.mock('@/config/featureFlags', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/config/featureFlags')>();
  return { ...actual, isRuntimeFlagEnabled: (key: string) => Boolean(state.flags[key]) };
});
vi.mock('@/pages/erp/erpShared', () => ({ ModuleGate: ({ children }: { children: React.ReactNode }) => <>{children}</> }));
vi.mock('@/pages/phase/phaseShared', () => ({
  PageShell: ({ title, children }: { title: string; children: React.ReactNode }) => (
    <section aria-label={title}>
      <h1>{title}</h1>
      {children}
    </section>
  ),
}));
vi.mock('@/api/resources', () => ({
  listProducts: async () => [
    { id: 1, name: 'Widget', sku: 'W-1' },
    { id: 2, name: 'Bolt', sku: 'B-1' },
  ],
  listWarehouses: async () => [{ id: 1, name: 'Main', code: 'M' }],
  listSuppliers: async () => [],
  listCustomers: async () => [],
}));
vi.mock('@/api/mfg', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/mfg')>();
  return {
    ...actual,
    listRecipes: vi.fn(async () => state.recipes),
    getCanMake: vi.fn(async () => ({ product: 1, qty: '40', limitedBy: 2, limitedByName: 'Bolt' })),
    quickProduction: vi.fn(async () => ({ id: 9, number: 'WO-9', productName: 'Widget' })),
    getMfgSettings: vi.fn(async () => ({
      id: 1,
      defaultIssueMode: 'AUTO_AT_RELEASE',
      backflushDefault: false,
      rmWarehouse: null,
      fgWarehouse: null,
      scrapWarehouse: null,
      quarantineWarehouse: null,
      backdateDays: 7,
      extraIssueApprovalPct: '5',
      finalReceiptTolerancePct: null,
      autoCloseDays: null,
      overReceiptPct: '0',
      itc04Frequency: 'HALF_YEARLY',
      jwInputLimitDays: 365,
      jwCapitalLimitDays: 1095,
      jwInputAlertDays: 30,
      jwCapitalAlertDays: 60,
    })),
  };
});

import { QuickProductionPage } from './QuickProductionPage';
import { MfgSettingsPage } from './MfgSettingsPage';
import { QualityPage } from './QualityPage';
import { quickProduction } from '@/api/mfg';

describe('Manufacturing pages', () => {
  beforeEach(() => {
    state.role = 'OWNER';
    state.recipes = [];
    state.flags = {};
    vi.clearAllMocks();
  });

  it('quick production warns when the item has no active recipe and will not post', async () => {
    renderRoutes([{ path: '/q', element: <QuickProductionPage /> }], '/q');
    await userEvent.click(await screen.findByLabelText(/what did you make/i));
    await userEvent.click(await screen.findByRole('option', { name: /Widget/ }));
    expect(await screen.findByText(/has no active recipe/i)).toBeTruthy();
    expect((screen.getByRole('button', { name: /record production/i }) as HTMLButtonElement).disabled).toBe(true);
  });

  it('quick production shows how many can be made and posts once with a key', async () => {
    state.recipes = [{ id: 3, product: 1, status: 'ACTIVE' }];
    renderRoutes([{ path: '/q', element: <QuickProductionPage /> }], '/q');
    await userEvent.click(await screen.findByLabelText(/what did you make/i));
    await userEvent.click(await screen.findByRole('option', { name: /Widget/ }));
    expect(await screen.findByText('40')).toBeTruthy();
    await userEvent.type(screen.getByLabelText(/^quantity/i), '5');
    const button = screen.getByRole('button', { name: /record production/i }) as HTMLButtonElement;
    await waitFor(() => expect(button.disabled).toBe(false));
    await userEvent.click(button);
    await waitFor(() => expect(quickProduction).toHaveBeenCalledTimes(1));
    const [body, key] = vi.mocked(quickProduction).mock.calls[0];
    expect(body).toMatchObject({ product: 1, qty: '5' });
    expect(typeof key).toBe('string');
    expect(await screen.findByText(/WO-9/)).toBeTruthy();
  });

  it('quick production is read-only for a role that cannot post', async () => {
    state.role = 'AUDITOR';
    state.recipes = [{ id: 3, product: 1, status: 'ACTIVE' }];
    renderRoutes([{ path: '/q', element: <QuickProductionPage /> }], '/q');
    await userEvent.click(await screen.findByLabelText(/what did you make/i));
    await userEvent.click(await screen.findByRole('option', { name: /Widget/ }));
    await userEvent.type(screen.getByLabelText(/^quantity/i), '5');
    expect((screen.getByRole('button', { name: /record production/i }) as HTMLButtonElement).disabled).toBe(true);
  });

  it('a sub-module that is switched off explains itself instead of loading', async () => {
    renderRoutes([{ path: '/quality', element: <QualityPage /> }], '/quality');
    expect(await screen.findByText(/not switched on for your company/i)).toBeTruthy();
  });

  it('settings load the saved mode and lock the form for a non-manager', async () => {
    state.role = 'INVENTORY_STAFF';
    renderRoutes([{ path: '/s', element: <MfgSettingsPage /> }], '/s');
    expect(await screen.findByText(/How work orders run/i, { selector: 'h6, p, span' })).toBeTruthy();
    expect((await screen.findByRole('button', { name: /^save$/i })) as HTMLButtonElement).toHaveProperty('disabled', true);
  });
});
