import { describe, expect, it } from 'vitest';
import { creditLimitExceeded, projectedCreditExposure } from '@/utils/creditExposure';

describe('creditLimitExceeded', () => {
  it('adds a new draft to ledger outstanding', () => {
    expect(projectedCreditExposure({ outstanding: 100, draftTotal: 50 })).toBe(150);
    expect(creditLimitExceeded({ limit: 140, outstanding: 100, draftTotal: 50 })).toBe(true);
    expect(creditLimitExceeded({ limit: 150, outstanding: 100, draftTotal: 50 })).toBe(false);
  });

  it('does not count a completed invoice twice while it is being amended', () => {
    expect(
      projectedCreditExposure({ outstanding: 100, draftTotal: 80, alreadyPosted: 100 }),
    ).toBe(80);
    expect(
      creditLimitExceeded({ limit: 100, outstanding: 100, draftTotal: 80, alreadyPosted: 100 }),
    ).toBe(false);
  });
});
