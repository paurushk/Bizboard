import { describe, expect, it } from 'vitest';
import type { Role, User } from '@/types/domain';
import { canPlanManufacturing, canSeeMfgCosts, canViewManufacturing, canWorkManufacturing } from './permissions';

const as = (role: Role) => ({ role }) as unknown as User;

describe('manufacturing role helpers mirror the server', () => {
  it('lets every back-office role read, but not sales or the policy desk', () => {
    for (const r of ['OWNER', 'MANAGER', 'INVENTORY_STAFF', 'ACCOUNTANT', 'AUDITOR', 'VIEWER'] as Role[]) {
      expect(canViewManufacturing(as(r))).toBe(true);
    }
    expect(canViewManufacturing(as('SALES_STAFF'))).toBe(false);
    expect(canViewManufacturing(as('POLICY_DESK'))).toBe(false);
    expect(canViewManufacturing(null)).toBe(false);
  });

  it('limits posting to owner, manager and inventory staff', () => {
    expect(canWorkManufacturing(as('INVENTORY_STAFF'))).toBe(true);
    expect(canWorkManufacturing(as('ACCOUNTANT'))).toBe(false);
    expect(canWorkManufacturing(as('VIEWER'))).toBe(false);
  });

  it('limits recipes, settings and reversals to owner and manager', () => {
    expect(canPlanManufacturing(as('MANAGER'))).toBe(true);
    expect(canPlanManufacturing(as('INVENTORY_STAFF'))).toBe(false);
  });

  it('shows costs to owner, manager, accountant and auditor only', () => {
    expect(canSeeMfgCosts(as('ACCOUNTANT'))).toBe(true);
    expect(canSeeMfgCosts(as('AUDITOR'))).toBe(true);
    expect(canSeeMfgCosts(as('INVENTORY_STAFF'))).toBe(false);
  });
});
