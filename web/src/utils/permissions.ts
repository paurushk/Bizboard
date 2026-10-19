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

export function isManager(role: Role): boolean {
  return role === 'MANAGER';
}

export function canManageUsers(user: User | null): boolean {
  return !!user && isOwner(user.role);
}

/** GST Guard override (OWNER/MANAGER only) — mirrors the backend gate in
 * reporting.gst_guard.gst_guard_override_membership. */
export function canOverrideGstGuard(user: User | null): boolean {
  return !!user && (isOwner(user.role) || isManager(user.role));
}

/** Payment promise creation (OWNER/MANAGER/ACCOUNTANT) — mirrors the backend
 * gate in payments.promise_to_pay. */
export function canManagePaymentPromises(user: User | null): boolean {
  return !!user && (isOwner(user.role) || isManager(user.role) || isAccountant(user.role));
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

/**
 * Importing a bill creates a draft document, so the importer must also be
 * allowed to create that document (same rule as the API: an import-only user
 * would otherwise land on a forbidden page after committing).
 */
export function canImportSalesBill(user: User | null): boolean {
  return canImport(user) && canCreateSales(user);
}

export function canImportPurchaseBill(user: User | null): boolean {
  return canImport(user) && canCreatePurchases(user);
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

/** TDS / TCS worksheets: the owner, or an accountant who may read financial reports. Mirrors the API. */
export function canViewTaxWorksheets(user: User | null): boolean {
  if (!user) return false;
  return isOwner(user.role) || (isAccountant(user.role) && user.canViewFinancialReports === true);
}

/** Cost of goods and gross margin: owner, or an accountant who may read financial reports. Mirrors the API. */
export function canViewMargins(user: User | null): boolean {
  return canViewTaxWorksheets(user);
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

/** Customer care, jobs and contracts: anyone with the sales right may work in them, and a viewer may read (D1). */
export function canViewCareSales(user: User | null): boolean {
  return !!user && (isViewer(user.role) || canCreateSales(user));
}

/** Supplier complaints follow the purchases right; a viewer may read. */
export function canViewCarePurchases(user: User | null): boolean {
  if (!user) return false;
  return isViewer(user.role) || isOwner(user.role) || user.canCreatePurchases === true;
}

/** Create / complete sales credit & debit notes. Mirrors the backend
 * CanCreateOrCompleteNotes: Owner, Accountant, or anyone with the sales flag. */
export function canIssueNotes(user: User | null): boolean {
  if (!user || isViewer(user.role)) return false;
  return isOwner(user.role) || isAccountant(user.role) || user.canCreateSales === true;
}

export function canCreatePurchases(user: User | null): boolean {
  if (!user || isViewer(user.role)) return false;
  return isOwner(user.role) || user.canCreatePurchases === true;
}

/** Post / reverse journals and edit the books masters (mirrors backend CanPostJournals). */
export function canPostJournals(user: User | null): boolean {
  if (!user || isViewer(user.role)) return false;
  return isOwner(user.role) || user.canPostJournals === true;
}

export function canCreatePayments(user: User | null): boolean {
  if (!user || isViewer(user.role)) return false;
  return isOwner(user.role) || user.canCreatePayments === true;
}

/** POS settles via receipts — needs sales create AND payments create (CR-003). */
export function canAccessPos(user: User | null): boolean {
  return canCreateSales(user) && canCreatePayments(user);
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
  // Same rule as the server (CanViewInventorySurfaces): anyone who sells or buys needs to see stock.
  return (
    canAdjustInventory(user) ||
    canViewFinancialReports(user) ||
    canCreateSales(user) ||
    canCreatePurchases(user)
  );
}

export function canAccessSettings(user: User | null): boolean {
  return canManageUsers(user) || canManageGst(user) || canImport(user) || canExport(user);
}

/** Correcting a closed till is for a manager or the owner — mirrors accounting.cash_shifts. */
export function canCorrectClosedTill(user: User | null): boolean {
  return !!user && (isOwner(user.role) || isManager(user.role));
}
