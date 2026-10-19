import { describe, expect, it } from 'vitest';
import type { User } from '@/types/domain';
import { canViewCarePurchases, canViewCareSales } from './permissions';

const user = (over: Partial<User>): User => ({ id: 1, email: 'a@x.test', fullName: 'A', role: 'SALES_STAFF', canManageInventory: false, canImport: false, companyId: 1, ...over });

describe('care and job screen access', () => {
  it('lets the owner, anyone with the sales right, and a viewer open the screens', () => {
    expect(canViewCareSales(user({ role: 'OWNER' }))).toBe(true);
    expect(canViewCareSales(user({ canCreateSales: true }))).toBe(true);
    expect(canViewCareSales(user({ role: 'VIEWER' }))).toBe(true);
  });

  it('keeps out someone who has neither the sales right nor a viewer role', () => {
    expect(canViewCareSales(user({ canCreateSales: false }))).toBe(false);
    expect(canViewCareSales(null)).toBe(false);
  });

  it('follows the purchases right for supplier complaints', () => {
    expect(canViewCarePurchases(user({ canCreatePurchases: true }))).toBe(true);
    expect(canViewCarePurchases(user({ role: 'OWNER' }))).toBe(true);
    expect(canViewCarePurchases(user({ role: 'VIEWER' }))).toBe(true);
    expect(canViewCarePurchases(user({ canCreateSales: true, canCreatePurchases: false }))).toBe(false);
  });
});
