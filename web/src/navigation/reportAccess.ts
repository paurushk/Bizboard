import type { User } from '@/types/domain';
import { isAccountingFeatureEnabled, isGstrReportsEnabled, isTdsEnabled } from '@/config/features';
import { canViewFinancialReports, canViewMargins, canViewTaxWorksheets } from '@/utils/permissions';

/**
 * RPT-09: one rule per report family, used by BOTH the menu and the route guard so a menu
 * item can never lead to a "not allowed" page. Mirrors the API permission for the same data.
 */

/** Trial Balance, P&L, Balance Sheet, Books Health: the company's books must be on. */
export function canViewAccountingReports(user: User | null): boolean {
  // CR-162: company.accountingEnabled activates this dynamically; the build flag alone must not.
  return (
    isAccountingFeatureEnabled(user?.company?.accountingEnabled) &&
    Boolean(user?.company?.accountingEnabled) &&
    canViewFinancialReports(user)
  );
}

/** GSTR-1/3B/4/9, CMP-08, 2B, Missing bills, GST Health, Rate back-scan. */
export function canViewGstrReports(user: User | null): boolean {
  return isGstrReportsEnabled() && canViewFinancialReports(user);
}

/** TDS / TCS worksheets: owner or accountant (API: CanViewTaxWorksheets). */
export function canViewTdsReports(user: User | null): boolean {
  return isTdsEnabled() && canViewTaxWorksheets(user);
}

/** Invoice Profit and its rollup show cost and margin: owner or accountant (API: CanViewMargins). */
export function canViewMarginReports(user: User | null): boolean {
  return canViewFinancialReports(user) && canViewMargins(user);
}
