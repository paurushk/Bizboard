import type { Role, User } from '@/types/domain';

export function isOwner(role: Role): boolean {
  return role === 'OWNER';
}

export function canManageUsers(user: User | null): boolean {
  return !!user && isOwner(user.role);
}

export function canManageGst(user: User | null): boolean {
  return !!user && isOwner(user.role);
}

export function canAdjustInventory(user: User | null): boolean {
  return !!user && (user.canManageInventory || isOwner(user.role));
}

export function canImport(user: User | null): boolean {
  return !!user && (user.canImport || isOwner(user.role));
}

export function canCancelDocuments(user: User | null): boolean {
  return !!user && (user.canCancelDocuments || isOwner(user.role));
}

export function canViewFinancialReports(user: User | null): boolean {
  // BUG-319: the backend flag now defaults to false (least privilege, like
  // its sibling capability flags) — mirror that here instead of treating a
  // missing/undefined value as permissive.
  return !!user && (user.canViewFinancialReports === true || isOwner(user.role));
}

export function canExport(user: User | null): boolean {
  return !!user && (user.canExport || isOwner(user.role));
}

export function canAccessSettings(user: User | null): boolean {
  return canManageUsers(user) || canManageGst(user) || canImport(user);
}
