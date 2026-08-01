import { describe, expect, it } from 'vitest';
import {
  canAdjustInventory,
  canCancelDocuments,
  canExport,
  canImport,
  canManageGst,
  canManageUsers,
  canViewFinancialReports,
  isOwner,
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
});
