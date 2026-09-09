import { describe, expect, it, vi } from 'vitest';
import { filterNav, isNavPathActive, isReallyReachable } from './menu';
import type { User } from '@/types/domain';
import { mockSalesUser } from '@/mocks/data';

vi.mock('@/config/featureFlags', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/config/featureFlags')>();
  return {
    ...actual,
    isRuntimeFlagEnabled: (key: string) =>
      Boolean((globalThis as { __ff?: Record<string, boolean> }).__ff?.[key]),
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
