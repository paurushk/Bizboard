import { describe, expect, it, vi } from 'vitest';
import type { User } from '@/types/domain';

vi.mock('@/config/features', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/config/features')>();
  return {
    ...actual,
    // The build flag is on everywhere; only the company's own setting should decide.
    isAccountingFeatureEnabled: () => true,
    isGstrReportsEnabled: () => true,
    isTdsEnabled: () => true,
  };
});

import { filterNav } from './menu';
import { canViewAccountingReports, canViewGstrReports, canViewMarginReports, canViewTdsReports } from './reportAccess';

function user(role: string, extra: Record<string, unknown> = {}, accountingEnabled = true): User {
  return { id: 1, role, company: { accountingEnabled }, ...extra } as unknown as User;
}

const USERS: Array<[string, User]> = [
  ['owner', user('OWNER')],
  ['owner, books off', user('OWNER', {}, false)],
  ['accountant with reports', user('ACCOUNTANT', { canViewFinancialReports: true })],
  ['accountant without reports', user('ACCOUNTANT', { canViewFinancialReports: false })],
  ['manager with reports', user('MANAGER', { canViewFinancialReports: true })],
  ['sales staff', user('SALES_STAFF')],
];

type NavNode = { id: string; children?: NavNode[] };
function collect(node: NavNode): string[] {
  return [node.id, ...(node.children ?? []).flatMap(collect)];
}

function reportIds(u: User): Set<string> {
  const reports = filterNav(u).find((i) => i.id === 'reports');
  return new Set(reports ? collect(reports as NavNode) : []);
}

describe('RPT-09 report menu items match the route guard', () => {
  it.each(USERS)('%s', (_name, u) => {
    const ids = reportIds(u);
    for (const id of ['trial-balance', 'profit-and-loss', 'balance-sheet', 'books-health']) {
      expect(ids.has(id), id).toBe(canViewAccountingReports(u));
    }
    for (const id of ['report-gstr1', 'report-gstr3b', 'report-gst-health', 'report-gst-rate-exposure']) {
      expect(ids.has(id), id).toBe(canViewGstrReports(u));
    }
    expect(ids.has('report-tds-tcs')).toBe(canViewTdsReports(u));
    expect(ids.has('report-invoice-profit')).toBe(canViewMarginReports(u));
  });

  it('a company with books off never sees the accounting reports, even with the build flag on', () => {
    expect(canViewAccountingReports(user('OWNER', {}, false))).toBe(false);
  });

  it('TDS/TCS worksheets: owner and accountant only', () => {
    expect(canViewTdsReports(user('OWNER'))).toBe(true);
    expect(canViewTdsReports(user('ACCOUNTANT', { canViewFinancialReports: true }))).toBe(true);
    expect(canViewTdsReports(user('ACCOUNTANT', { canViewFinancialReports: false }))).toBe(false);
    expect(canViewTdsReports(user('MANAGER', { canViewFinancialReports: true }))).toBe(false);
  });

  it('groups the Reports menu and keeps every item id', () => {
    const owner = user('OWNER', { canViewFinancialReports: true });
    const reports = filterNav(owner).find((i) => i.id === 'reports');
    const groups = (reports?.children ?? []).filter((c) => c.children).map((c) => c.id);
    expect(groups).toEqual(['reports-operational', 'reports-compliance', 'reports-books']);
    expect(reports?.children?.[0]?.id).toBe('report-close-month');
    const ids = reportIds(owner);
    for (const id of ['report-sales', 'cash-book', 'report-gstr1', 'report-tds-tcs', 'report-tds-receivable', 'trial-balance', 'books-health']) {
      expect(ids.has(id), id).toBe(true);
    }
  });

  it('drops the Books group, not just its items, when books are off', () => {
    const reports = filterNav(user('OWNER', { canViewFinancialReports: true }, false)).find((i) => i.id === 'reports');
    expect((reports?.children ?? []).some((c) => c.id === 'reports-books')).toBe(false);
  });

  it('keeps GSTR-6/7/8 out unless the extended-returns flag is on (nested items stay gated)', () => {
    const ids = reportIds(user('OWNER', { canViewFinancialReports: true }));
    for (const id of ['report-gstr6', 'report-gstr7', 'report-gstr8']) expect(ids.has(id), id).toBe(false);
  });

  it('margins: owner and accountant with report access only', () => {
    expect(canViewMarginReports(user('OWNER'))).toBe(true);
    expect(canViewMarginReports(user('ACCOUNTANT', { canViewFinancialReports: true }))).toBe(true);
    expect(canViewMarginReports(user('MANAGER', { canViewFinancialReports: true }))).toBe(false);
    expect(canViewMarginReports(user('ACCOUNTANT', { canViewFinancialReports: false }))).toBe(false);
  });
});
