import { afterEach, describe, expect, it, vi } from 'vitest';
import type { User } from '@/types/domain';
import { filterNav } from './menu';

vi.mock('@/config/featureFlags', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/config/featureFlags')>();
  const flags = () => (globalThis as { __ff?: Record<string, boolean> }).__ff;
  return {
    ...actual,
    isRuntimeFlagEnabled: (key: string) => Boolean(flags()?.[key]),
    isMoneyHubEnabled: () => true,
    getCachedFeatureFlags: () => {
      const current = flags();
      return current && Object.keys(current).length > 0 ? current : null;
    },
  };
});

const user = (role: string) => ({ id: 1, role, permissions: [] }) as unknown as User;
const setFlags = (f: Record<string, boolean>) => {
  (globalThis as { __ff?: Record<string, boolean> }).__ff = f;
};
const children = (u: User) => (filterNav(u).find((i) => i.id === 'manufacturing')?.children ?? []).map((c) => c.id);

describe('Manufacturing menu', () => {
  afterEach(() => setFlags({}));

  it('shows only the always-on screens until a sub-module is granted', () => {
    setFlags({ ENABLE_MANUFACTURING: true });
    const ids = children(user('OWNER'));
    expect(ids).toEqual(expect.arrayContaining(['mfg-quick', 'boms', 'work-orders', 'mfg-reports', 'mfg-settings']));
    for (const gated of ['mfg-planning', 'mfg-quality', 'mfg-job-work', 'mfg-shop-floor']) expect(ids).not.toContain(gated);
  });

  it('adds each sub-module when its switch is on', () => {
    setFlags({ ENABLE_MANUFACTURING: true, MFG_PLANNING: true, MFG_QUALITY: true, MFG_JOB_WORK: true, MFG_SHOP_FLOOR: true });
    expect(children(user('OWNER'))).toEqual(expect.arrayContaining(['mfg-planning', 'mfg-quality', 'mfg-job-work', 'mfg-shop-floor']));
  });

  it('hides posting and settings from a role that may only read', () => {
    setFlags({ ENABLE_MANUFACTURING: true });
    const ids = children(user('AUDITOR'));
    expect(ids).toContain('work-orders');
    expect(ids).not.toContain('mfg-quick');
    expect(ids).not.toContain('mfg-settings');
  });

  it('is absent for a sales user and when the module is off', () => {
    setFlags({ ENABLE_MANUFACTURING: true });
    expect(filterNav(user('SALES_STAFF')).some((i) => i.id === 'manufacturing')).toBe(false);
    setFlags({});
    expect(filterNav(user('OWNER')).some((i) => i.id === 'manufacturing')).toBe(false);
  });
});
