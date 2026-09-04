import { useAuth } from '@/auth/AuthContext';
import type { User } from '@/types/domain';
import {
  canAdjustInventory,
  canCancelDocuments,
  canCreateSales,
  canCreatePurchases,
  canImport,
  canViewFinancialReports,
  isOwner,
} from '@/utils/permissions';
import type { HelpPermission } from './types';

export function userHasHelpPermission(user: User | null, permission: HelpPermission): boolean {
  if (!user) return false;
  switch (permission) {
    case 'owner':
      return isOwner(user.role);
    case 'can_create_sales':
      return canCreateSales(user);
    case 'can_create_purchases':
      return canCreatePurchases(user);
    case 'can_manage_inventory':
      return canAdjustInventory(user);
    case 'can_import':
      return canImport(user);
    case 'can_post_journals':
      return isOwner(user.role) || user.canPostJournals === true;
    case 'can_cancel_documents':
      return canCancelDocuments(user);
    case 'can_view_financial_reports':
      return canViewFinancialReports(user);
    default:
      return false;
  }
}

export function interpolateDestination(destination: string, params: Record<string, string | number | undefined>): string {
  let out = destination;
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === '') continue;
    // F3-071: replace whole `:param` tokens only. A plain replaceAll(':id', …)
    // also rewrites the `:id` inside `:invoiceId`, so order-dependent corruption
    // like `/x/:invoiceId` -> `/x/5nvoiceId` was possible. The negative
    // lookahead anchors the token to a param-name boundary.
    out = out.replace(new RegExp(`:${key}(?![A-Za-z0-9_])`, 'g'), String(value));
  }
  if (/:\w+/.test(out)) return '';
  return out;
}

export function useHelpUser(): User | null {
  return useAuth().user;
}
