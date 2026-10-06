import { describe, expect, it, vi } from 'vitest';
import { clearNavNotReady, markNavNotReady } from './notReadyNav';
import { filterNav, isNavPathActive, isReallyReachable } from './menu';
import type { User } from '@/types/domain';
import { mockSalesUser } from '@/mocks/data';

vi.mock('@/config/featureFlags', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/config/featureFlags')>();
  const flags = () => (globalThis as { __ff?: Record<string, boolean> }).__ff;
  return {
    ...actual,
    isRuntimeFlagEnabled: (key: string) => Boolean(flags()?.[key]),
    getCachedFeatureFlags: () => {
      const current = flags();
      return current && Object.keys(current).length > 0 ? current : null;
    },
  };
});

describe('isNavPathActive (R-065)', () => {
  it('highlights Sales History on nested invoice routes', () => {
    expect(isNavPathActive('/sales/history', '/sales/history')).toBe(true);
    expect(isNavPathActive('/sales/history/123', '/sales/history')).toBe(true);
    expect(isNavPathActive('/sales/history/123/edit', '/sales/history')).toBe(true);
  });

  it('does not treat /sales-returns as Sales History', () => {
    expect(isNavPathActive('/sales-returns', '/sales/history')).toBe(false);
    expect(isNavPathActive('/sales', '/sales/history')).toBe(false);
    expect(isNavPathActive('/sales/new', '/sales/history')).toBe(false);
  });

  it('strips query strings and trailing slashes', () => {
    expect(isNavPathActive('/sales/history/123?helpAction=cancel', '/sales/history')).toBe(true);
    expect(isNavPathActive('/sales/history/', '/sales/history')).toBe(true);
  });
});

describe('account aggregator nav (R-063 / R-087)', () => {
  const owner = {
    id: 1,
    role: 'OWNER',
    permissions: ['payments.view', 'bank.recon'],
  } as unknown as User;

  function aaVisible(): boolean {
    const payments = filterNav(owner).find((i) => i.id === 'payments');
    return Boolean(payments?.children?.some((c) => c.id === 'account-aggregator'));
  }

  it('hides AA unless ENABLE_ACCOUNT_AGGREGATOR and ENABLE_AA_CONSENT', () => {
    (globalThis as { __ff?: Record<string, boolean> }).__ff = {};
    expect(aaVisible()).toBe(false);
    expect(isReallyReachable(owner, '/payments/account-aggregator')).toBe(false);

    (globalThis as { __ff?: Record<string, boolean> }).__ff = {
      ENABLE_ACCOUNT_AGGREGATOR: true,
    };
    expect(aaVisible()).toBe(false);

    (globalThis as { __ff?: Record<string, boolean> }).__ff = {
      ENABLE_ACCOUNT_AGGREGATOR: true,
      ENABLE_AA_CONSENT: true,
    };
    expect(aaVisible()).toBe(true);
  });
});

describe('customer portal nav (COMP-003)', () => {
  const sales = {
    ...mockSalesUser,
    canCreateSales: true,
  } as User;

  function portalVisible(user: User = sales): boolean {
    const payments = filterNav(user).find((item) => item.id === 'payments');
    return Boolean(payments?.children?.some((child) => child.id === 'customer-portal'));
  }

  it('stays hidden until ENABLE_CUSTOMER_PORTAL is on for someone who can create sales', () => {
    (globalThis as { __ff?: Record<string, boolean> }).__ff = {};
    expect(portalVisible()).toBe(false);
    expect(isReallyReachable(sales, '/portal')).toBe(false);

    (globalThis as { __ff?: Record<string, boolean> }).__ff = { ENABLE_CUSTOMER_PORTAL: true };
    expect(portalVisible()).toBe(true);

    const viewer = { id: 3, role: 'VIEWER', canCreateSales: true } as unknown as User;
    expect(portalVisible(viewer)).toBe(false);
  });
});

describe('POS nav gate (CR-003)', () => {
  it('pos_hidden_without_can_create_payments', () => {
    (globalThis as { __ff?: Record<string, boolean> }).__ff = { ENABLE_POS: true };

    const salesOnly = {
      ...mockSalesUser,
      canCreateSales: true,
      canCreatePayments: false,
    } as User;
    expect(filterNav(salesOnly).some((i) => i.id === 'pos')).toBe(false);
    expect(isReallyReachable(salesOnly, '/pos')).toBe(false);

    const both = {
      ...mockSalesUser,
      canCreateSales: true,
      canCreatePayments: true,
    } as User;
    expect(filterNav(both).some((i) => i.id === 'pos')).toBe(true);
    expect(isReallyReachable(both, '/pos')).toBe(true);
  });
});

describe('sales nav length', () => {
  const owner = {
    id: 1,
    role: 'OWNER',
    canViewFinancialReports: true,
    canCreateSales: true,
    canCreatePayments: true,
    canImport: true,
  } as unknown as User;

  it('keeps the daily sales links up front and nests the rest under More', () => {
    const sales = filterNav(owner).find((item) => item.id === 'sales');
    const ids = sales?.children?.map((child) => child.id) ?? [];
    expect(ids).toContain('new-invoice');
    expect(ids).toContain('receipts');
    expect(ids).toContain('customers');
    expect(ids).not.toContain('sales-returns');
    const more = sales?.children?.find((child) => child.id === 'sales-more');
    expect(more?.children?.some((child) => child.id === 'sales-returns')).toBe(true);
    expect(isReallyReachable(owner, '/sales/returns')).toBe(true);
  });

  it('keeps bills of entry hidden and hides the dashboard from sales staff', () => {
    expect(isReallyReachable(owner, '/purchases/bills-of-entry')).toBe(false);
    const staff = filterNav(mockSalesUser);
    expect(staff.some((item) => item.id === 'dashboard')).toBe(false);
    expect(staff.find((item) => item.id === 'sales')?.children?.some((child) => child.id === 'sales-more')).toBe(true);
  });
});

describe('vision plan nav', () => {
  const owner = { id: 1, role: 'OWNER', canViewFinancialReports: true } as unknown as User;

  it('shows collections to a report reader, and purchase planning and the pack wizard only when their flags are on', () => {
    (globalThis as { __ff?: Record<string, boolean> }).__ff = {};
    const hidden = filterNav(owner);
    expect(hidden.find((item) => item.id === 'payments')?.children?.some((child) => child.id === 'collections')).toBe(true);
    expect(isReallyReachable(owner, '/payments/collections')).toBe(true);
    const staff = { id: 2, role: 'SALES_STAFF', canViewFinancialReports: false } as unknown as User;
    expect(filterNav(staff).find((item) => item.id === 'payments')?.children?.some((child) => child.id === 'collections') ?? false).toBe(false);
    expect(hidden.find((item) => item.id === 'inventory')?.children?.some((child) => child.id === 'purchase-planning')).toBe(false);
    expect(hidden.find((item) => item.id === 'settings')?.children?.some((child) => child.id === 'pack-wizard')).toBe(false);

    (globalThis as { __ff?: Record<string, boolean> }).__ff = {
      ENABLE_PREDICTIVE_DUNNING: true,
      ENABLE_PURCHASE_PLANNING: true,
      ENABLE_ARCHETYPE_PACKS: true,
    };
    const shown = filterNav(owner);
    expect(shown.find((item) => item.id === 'payments')?.children?.some((child) => child.id === 'collections')).toBe(true);
    expect(shown.find((item) => item.id === 'inventory')?.children?.some((child) => child.id === 'purchase-planning')).toBe(true);
    expect(shown.find((item) => item.id === 'settings')?.children?.some((child) => child.id === 'pack-wizard')).toBe(true);
    expect(isReallyReachable(owner, '/payments/collections')).toBe(true);
    expect(isReallyReachable(owner, '/inventory/purchase-planning')).toBe(true);
    expect(isReallyReachable(owner, '/settings/packs')).toBe(true);
  });

  it('permanently hides distractive out-of-scope desks (tickets, insurance, contracts, telegram)', () => {
    const nav = filterNav(owner);
    const ids = nav.flatMap((item) => [item.id, ...(item.children?.map((c) => c.id) ?? [])]);
    expect(ids).not.toContain('tickets');
    expect(ids).not.toContain('shared-tickets');
    expect(ids).not.toContain('insurance');
    expect(ids).not.toContain('contracts');
    expect(ids).not.toContain('telegram');
  });
});

describe('flag-gated release surfaces (full-demo profile)', () => {
  const owner = {
    id: 1,
    role: 'OWNER',
    canViewFinancialReports: true,
    canCreateSales: true,
    canCreatePayments: true,
    canCreatePurchases: true,
    canImport: true,
  } as unknown as User;
  const allIds = (user: User): string[] =>
    filterNav(user).flatMap((s) => [s.id, ...(s.children ?? []).map((c) => c.id)]);
  const ff = (flags: Record<string, boolean>) => {
    (globalThis as { __ff?: Record<string, boolean> }).__ff = flags;
  };

  it('keeps bills of entry, fixed assets, Telegram and GSTR-9 hidden while their flags are off', () => {
    ff({});
    const ids = allIds(owner);
    for (const id of ['bills-of-entry', 'fixed-assets', 'telegram', 'report-gstr9']) {
      expect(ids).not.toContain(id);
    }
  });

  it('shows bills of entry and Telegram when their flags are on, with no build-time switch', () => {
    ff({ ENABLE_BOE: true, ENABLE_TELEGRAM: true });
    const ids = allIds(owner);
    expect(ids).toContain('bills-of-entry');
    expect(ids).toContain('telegram');
    ff({});
  });

  it('hides a nav id marked not-ready and shows it again when cleared', () => {
    ff({ ENABLE_BOE: true });
    expect(allIds(owner)).toContain('bills-of-entry');
    markNavNotReady('bills-of-entry');
    expect(allIds(owner)).not.toContain('bills-of-entry');
    clearNavNotReady();
    expect(allIds(owner)).toContain('bills-of-entry');
    ff({});
  });

  it('keeps GSTR-6, 7 and 8 out of the menu even with every flag on (not-ready list)', () => {
    ff({ ENABLE_GSTR: true, ENABLE_GSTR_EXTENDED: true });
    const ids = allIds(owner);
    for (const id of ['report-gstr6', 'report-gstr7', 'report-gstr8']) expect(ids).not.toContain(id);
    ff({});
  });

  it('shows the extended GSTR worksheets only with ENABLE_GSTR_EXTENDED', () => {
    ff({ ENABLE_GSTR: true });
    expect(allIds(owner)).not.toContain('report-gstr9');
    ff({ ENABLE_GSTR: true, ENABLE_GSTR_EXTENDED: true });
    expect(allIds(owner)).toEqual(expect.arrayContaining(['report-gstr2b', 'report-gstr4', 'report-gstr9']));
    ff({});
  });

  it('G9 full menu is larger than the pack sidebar', () => {
    const flags: Record<string, boolean> = {
      ENABLE_BOE: true,
      ENABLE_TELEGRAM: true,
      ENABLE_FIXED_ASSETS: true,
      ENABLE_SUPPORT_TICKETS: true,
      ENABLE_INSURANCE: true,
      ENABLE_CONTRACTS: true,
      ENABLE_GSTR: true,
      ENABLE_GSTR_EXTENDED: true,
      ENABLE_CRM: true,
      ENABLE_MANUFACTURING: true,
      ENABLE_PAYROLL: true,
      ENABLE_COMPLAINTS: true,
      ENABLE_WORKSHOP: true,
      ENABLE_PROJECTS: true,
      ENABLE_REFERRALS: true,
    };
    ff(flags);
    const full = allIds(owner);
    expect(full).toEqual(expect.arrayContaining(['manufacturing', 'payroll', 'crm', 'complaints']));
    ff({ ...flags, NAV_PACK_DEFAULT: true });
    const pack = allIds(owner);
    expect(pack.length).toBeLessThan(full.length);
    for (const id of ['insights', 'manufacturing', 'payroll', 'crm', 'complaints', 'tickets', 'insurance', 'contracts']) {
      expect(pack).not.toContain(id);
    }
    ff({});
  });
});
