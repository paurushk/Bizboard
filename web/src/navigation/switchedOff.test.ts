import { beforeEach, describe, expect, it, vi } from 'vitest';

let flags: Record<string, boolean> | null = null;

vi.mock('@/config/featureFlags', () => ({
  getCachedFeatureFlags: () => flags,
  isRuntimeFlagEnabled: (key: string) => Boolean(flags?.[key]),
  isMoneyHubEnabled: () => true,
}));

const { switchedOffFlag } = await import('./menu');

/** BB-100: a switched-off page opened from a bookmark shows a notice, not a raw "Not found". */
describe('switchedOffFlag', () => {
  beforeEach(() => {
    flags = {};
  });

  it('names the flag for a switched-off page and its sub-paths', () => {
    expect(switchedOffFlag('/purchases/bills-of-entry')).toBe('ENABLE_BOE');
    expect(switchedOffFlag('/purchases/bills-of-entry/')).toBe('ENABLE_BOE');
  });

  it('lets the page through once the company has the flag', () => {
    flags = { ENABLE_BOE: true };
    expect(switchedOffFlag('/purchases/bills-of-entry')).toBeNull();
  });

  it('never blocks ordinary pages', () => {
    for (const path of ['/', '/sales/history', '/purchases', '/reports/day-book', '/settings/billing']) {
      expect(switchedOffFlag(path), path).toBeNull();
    }
  });

  it('blocks nothing before flags have loaded', () => {
    flags = null;
    expect(switchedOffFlag('/purchases/bills-of-entry')).toBeNull();
  });
});
