import { describe, expect, it } from 'vitest';
import { creditExceedsBalance } from './returnHelpers';

describe('creditExceedsBalance', () => {
  it('is false without an invoice or a credit figure', () => {
    expect(creditExceedsBalance(null, 50)).toBe(false);
    expect(creditExceedsBalance({ balance: '100', grandTotal: '100' }, null)).toBe(false);
  });
  it('is false when the credit fits inside what is still owed', () => {
    expect(creditExceedsBalance({ balance: '100', grandTotal: '100' }, 100)).toBe(false);
    expect(creditExceedsBalance({ balance: '300', grandTotal: '590' }, 118)).toBe(false);
  });
  it('is true when the credit is larger than the balance (excess becomes advance)', () => {
    expect(creditExceedsBalance({ balance: '0', grandTotal: '100' }, 50)).toBe(true);
    expect(creditExceedsBalance({ balance: '40', grandTotal: '100' }, 59)).toBe(true);
  });
  it('treats a missing balance as the full invoice total', () => {
    expect(creditExceedsBalance({ grandTotal: '100' } as never, 100)).toBe(false);
  });
});
