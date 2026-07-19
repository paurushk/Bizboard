import { describe, expect, it } from 'vitest';
import {
  canAdjustInventory,
  canImport,
  canManageGst,
  canManageUsers,
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
});
