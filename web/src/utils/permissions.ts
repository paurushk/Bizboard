import type { Role, User } from '@/types/domain';

export function isOwner(role: Role): boolean {
  return role === 'OWNER';
}

export function isViewer(role: Role): boolean {
  return role === 'VIEWER';
}

export function isAccountant(role: Role): boolean {
  return role === 'ACCOUNTANT';
}

export function canManageUsers(user: User | null): boolean {
  return !!user && isOwner(user.role);
}

export function canManageManufacturing(user: User | null): boolean {
  // F1-021: isOwner already excludes VIEWER, so the extra isViewer guard was dead.
  return !!user && isOwner(user.role);
}

export function canManagePayroll(user: User | null): boolean {
  return !!user && isOwner(user.role);
}

export function canManageCrm(user: User | null): boolean {
  if (!user || isViewer(user.role)) return false;
  return isOwner(user.role) || user.canCreateSales === true;
}

export function canManageGst(user: User | null): boolean {
  return !!user && isOwner(user.role);
}

export function canAdjustInventory(user: User | null): boolean {
  return !!user && (user.canManageInventory === true || isOwner(user.role));
}

export function canImport(user: User | null): boolean {
  return !!user && (user.canImport === true || isOwner(user.role));
}

export function canCancelDocuments(user: User | null): boolean {
  return !!user && (user.canCancelDocuments === true || isOwner(user.role));
}

export function canViewFinancialReports(user: User | null): boolean {
  // BUG-319: the backend flag now defaults to false (least privilege, like
  // its sibling capability flags) — mirror that here instead of treating a
  // missing/undefined value as permissive.
  return !!user && (user.canViewFinancialReports === true || isOwner(user.role));
}

export function canViewAiInsights(user: User | null): boolean {
  if (!user) return false;
  // BB-000425: missing/undefined means AI off (default false).
  if (user.company?.aiFeaturesEnabled !== true) return false;
  // VIEWER / ACCOUNTANT defaults keep AI off unless explicitly flagged.
  if (isViewer(user.role)) return false;
  if (isAccountant(user.role)) return user.canViewAiInsights === true;
  return isOwner(user.role) || user.canViewAiInsights === true;
}

export function canUseAiAssistant(user: User | null): boolean {
  if (!user) return false;
  if (user.company?.aiFeaturesEnabled !== true) return false;
  return isOwner(user.role) || user.canUseAiAssistant === true;
}

export function canExport(user: User | null): boolean {
  return !!user && (user.canExport === true || isOwner(user.role));
}

export function canCreateSales(user: User | null): boolean {
  if (!user || isViewer(user.role)) return false;
  return isOwner(user.role) || user.canCreateSales === true;
}

export function canCreatePurchases(user: User | null): boolean {
  if (!user || isViewer(user.role)) return false;
  return isOwner(user.role) || user.canCreatePurchases === true;
}

export function canCreatePayments(user: User | null): boolean {
  if (!user || isViewer(user.role)) return false;
  return isOwner(user.role) || user.canCreatePayments === true;
}

/** Receipts / recon: payers or financial-report viewers — not sales-view-only. */
export function canViewPaymentSurfaces(user: User | null): boolean {
  if (!user || isViewer(user.role)) return false;
  return canCreatePayments(user) || canViewFinancialReports(user);
}

/** Bank recon is cash ops or financial reports — not sales-view-only. */
export function canViewBankRecon(user: User | null): boolean {
  return canCreatePayments(user) || canViewFinancialReports(user);
}

/** BB-000297: sales list/detail — not VIEWER; create-sales or financial reports. */
export function canViewSalesSurfaces(user: User | null): boolean {
  if (!user || isViewer(user.role)) return false;
  return canCreateSales(user) || canViewFinancialReports(user);
}

/** BB-000297: purchase list/detail — not VIEWER; create-purchases or financial reports. */
export function canViewPurchaseSurfaces(user: User | null): boolean {
  if (!user || isViewer(user.role)) return false;
  return canCreatePurchases(user) || canViewFinancialReports(user);
}

/** BB-000297: inventory list/detail read surfaces. */
export function canViewInventorySurfaces(user: User | null): boolean {
  if (!user || isViewer(user.role)) return false;
  return (
    canAdjustInventory(user) ||
    canViewFinancialReports(user)
  );
}

export function canAccessSettings(user: User | null): boolean {
  return canManageUsers(user) || canManageGst(user) || canImport(user) || canExport(user);
}
