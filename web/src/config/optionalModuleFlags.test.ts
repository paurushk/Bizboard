import { beforeEach, describe, expect, it, vi } from 'vitest';

const cache: { current: Record<string, boolean> | null } = { current: null };

vi.mock('@/config/featureFlags', () => ({
  getCachedFeatureFlags: () => cache.current,
  isRuntimeFlagEnabled: (key: string) => Boolean(cache.current?.[key]),
}));

import { isManufacturingEnabled, isPayrollEnabled } from '@/config/features';

describe('manufacturing and payroll stay gated like CRM', () => {
  beforeEach(() => {
    cache.current = null;
  });

  it('stays off until runtime flags load, then follows the company grant', () => {
    expect(isManufacturingEnabled()).toBe(false);
    expect(isPayrollEnabled()).toBe(false);
    cache.current = { ENABLE_MANUFACTURING: true, ENABLE_PAYROLL: false };
    expect(isManufacturingEnabled()).toBe(true);
    expect(isPayrollEnabled()).toBe(false);
  });
});
