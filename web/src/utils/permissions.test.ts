import { describe, expect, it } from 'vitest';
import {
  canAdjustInventory,
  canCancelDocuments,
  canCreatePurchases,
  canCreateSales,
  canExport,
  canImport,
  canManageGst,
  canManageUsers,
  canViewFinancialReports,
  canViewInventorySurfaces,
  canViewPurchaseSurfaces,
  canViewSalesSurfaces,
  isAccountant,
  isOwner,
  isViewer,
} from '@/utils/permissions';
import { mockSalesUser, mockUser } from '@/mocks/data';

describe('permissions', () => {
  it('allows owner to manage settings and inventory', () => {
    expect(canManageUsers(mockUser)).toBe(true);
    expect(canManageGst(mockUser)).toBe(true);
    expect(canAdjustInventory(mockUser)).toBe(true);
    expect(canImport(mockUser)).toBe(true);
  });

  it('locks sales staff out of GST/users/import', () => {
    expect(canManageUsers(mockSalesUser)).toBe(false);
    expect(canManageGst(mockSalesUser)).toBe(false);
    expect(canImport(mockSalesUser)).toBe(false);
    expect(canAdjustInventory(mockSalesUser)).toBe(false);
  });

  it('isOwner recognizes only the OWNER role', () => {
    expect(isOwner('OWNER')).toBe(true);
    expect(isOwner('SALES_STAFF')).toBe(false);
  });

  it('BUG-417: canCancelDocuments/canExport follow the per-user flag for staff', () => {
    expect(canCancelDocuments({ ...mockSalesUser, canCancelDocuments: true })).toBe(true);
    expect(canCancelDocuments({ ...mockSalesUser, canCancelDocuments: false })).toBe(false);
    expect(canExport({ ...mockSalesUser, canExport: true })).toBe(true);
    expect(canExport({ ...mockSalesUser, canExport: false })).toBe(false);
    // Owners always pass regardless of their own flag value.
    expect(canCancelDocuments({ ...mockUser, canCancelDocuments: false })).toBe(true);
  });

  it('BUG-319: canViewFinancialReports defaults to false for staff, not true', () => {
    expect(canViewFinancialReports({ ...mockSalesUser, canViewFinancialReports: false })).toBe(false);
    expect(canViewFinancialReports({ ...mockSalesUser, canViewFinancialReports: true })).toBe(true);
    // Owners always pass regardless of their own flag value.
    expect(canViewFinancialReports({ ...mockUser, canViewFinancialReports: false })).toBe(true);
  });

  it('BB-000018: canCreateSales denies staff when flag is false', () => {
    expect(canCreateSales({ ...mockSalesUser, canCreateSales: false })).toBe(false);
    expect(canCreateSales({ ...mockSalesUser, canCreateSales: true })).toBe(true);
    expect(canCreateSales({ ...mockUser, canCreateSales: false })).toBe(true);
  });

  it('VIEWER cannot create sales/purchases even if flags are true', () => {
    const viewer = {
      ...mockSalesUser,
      role: 'VIEWER' as const,
      canCreateSales: true,
      canCreatePurchases: true,
    };
    expect(isViewer('VIEWER')).toBe(true);
    expect(isAccountant('ACCOUNTANT')).toBe(true);
    expect(canCreateSales(viewer)).toBe(false);
    expect(canCreatePurchases(viewer)).toBe(false);
  });

  it('BB-000297: VIEWER cannot open sales/purchase/inventory list surfaces', () => {
    const viewer = {
      ...mockSalesUser,
      role: 'VIEWER' as const,
      canViewFinancialReports: true,
      canCreateSales: false,
      canCreatePurchases: false,
    };
    expect(canViewSalesSurfaces(viewer)).toBe(false);
    expect(canViewPurchaseSurfaces(viewer)).toBe(false);
    expect(canViewInventorySurfaces(viewer)).toBe(false);
  });
});
