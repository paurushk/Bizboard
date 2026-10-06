import { describe, expect, it } from 'vitest';
import { isOlderThanMs, isPastIso } from '@/utils/clock';

describe('clock helpers', () => {
  it('treats a past ISO time as past and a future one as not', () => {
    expect(isPastIso('2000-01-01T00:00:00Z')).toBe(true);
    expect(isPastIso('2999-01-01T00:00:00Z')).toBe(false);
  });

  it('is false for empty or unparseable input', () => {
    expect(isPastIso(null)).toBe(false);
    expect(isPastIso('')).toBe(false);
    expect(isPastIso('not a date')).toBe(false);
    expect(isOlderThanMs(undefined, 1000)).toBe(false);
    expect(isOlderThanMs('not a date', 1000)).toBe(false);
  });

  it('measures age against a window', () => {
    const tenSecondsAgo = new Date(Date.now() - 10_000).toISOString();
    expect(isOlderThanMs(tenSecondsAgo, 5_000)).toBe(true);
    expect(isOlderThanMs(tenSecondsAgo, 60_000)).toBe(false);
  });
});
