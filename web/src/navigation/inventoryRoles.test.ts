import { afterEach, describe, expect, it, vi } from 'vitest';
import { filterNav } from './menu';
import type { User } from '@/types/domain';

vi.mock('@/config/featureFlags', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/config/featureFlags')>();
  return {
    ...actual,
    isRuntimeFlagEnabled: () => true,
    isMoneyHubEnabled: () => true,
    getCachedFeatureFlags: () => ({ ENABLE_PURCHASE_PLANNING: true, ENABLE_REPLENISHMENT: true }),
  };
});

// The same capability defaults the server gives each role (accounts.CompanyUser.capability_defaults_for_role).
const ROLE_USERS: Record<string, Partial<User>> = {
  OWNER: { role: 'OWNER' },
  MANAGER: { role: 'MANAGER', canManageInventory: true, canViewFinancialReports: true, canCreateSales: true, canCreatePurchases: true },
  INVENTORY_STAFF: { role: 'INVENTORY_STAFF', canManageInventory: true, canCreatePurchases: true },
  SALES_STAFF: { role: 'SALES_STAFF', canCreateSales: true },
  ACCOUNTANT: { role: 'ACCOUNTANT', canViewFinancialReports: true, canCreatePurchases: true },
  AUDITOR: { role: 'AUDITOR', canViewFinancialReports: true },
  VIEWER: { role: 'VIEWER' },
};

const READ_SCREENS = ['products', 'current-stock', 'stock-ledger', 'low-stock', 'purchase-planning', 'demand-forecast', 'label-print', 'expiry-alerts'];
const MANAGE_SCREENS = ['stock-adjustment', 'warehouses', 'stock-counts', 'stock-transfers', 'serials'];

function inventoryMenu(role: string): string[] {
  const user = { id: 1, ...ROLE_USERS[role] } as User;
  return filterNav(user).find((item) => item.id === 'inventory')?.children?.map((child) => child.id) ?? [];
}

describe('inventory menu by role (matches the server permission matrix)', () => {
  afterEach(() => vi.clearAllMocks());

  it.each(['OWNER', 'MANAGER', 'INVENTORY_STAFF'])('%s sees every inventory screen', (role) => {
    expect(inventoryMenu(role).sort()).toEqual([...READ_SCREENS, ...MANAGE_SCREENS].sort());
  });

  it.each(['SALES_STAFF', 'ACCOUNTANT', 'AUDITOR'])('%s sees the read screens but none of the tools', (role) => {
    const shown = inventoryMenu(role);
    expect(shown.sort()).toEqual([...READ_SCREENS].sort());
    for (const id of MANAGE_SCREENS) expect(shown).not.toContain(id);
  });

  it('a viewer sees no inventory screen at all', () => {
    expect(inventoryMenu('VIEWER')).toEqual([]);
  });
});
