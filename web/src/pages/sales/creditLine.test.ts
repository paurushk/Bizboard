import { describe, expect, it } from 'vitest';
import { creditLineView } from './creditLine';

describe('creditLineView', () => {
  it('hides the line when the customer has no limit', () => {
    expect(creditLineView({ limit: 0, outstanding: 100, billTotal: 10 })).toBeNull();
  });

  it('shows remaining credit while owed plus this bill stays under 80% of the limit', () => {
    expect(creditLineView({ limit: 10000, outstanding: 1000, billTotal: 500 })).toEqual({
      severity: 'info',
      outstanding: 1000,
      limit: 10000,
      available: 9000,
    });
  });

  it('turns amber when owed plus this bill reaches 80% and still fits', () => {
    expect(creditLineView({ limit: 10000, outstanding: 8000, billTotal: 1000 })?.severity).toBe('warning');
    expect(creditLineView({ limit: 10000, outstanding: 7000, billTotal: 1500 })?.severity).toBe('warning');
  });

  it('turns red when this bill crosses the limit, and available stays limit minus what is already owed', () => {
    expect(creditLineView({ limit: 10000, outstanding: 7000, billTotal: 4000 })).toEqual({
      severity: 'error',
      outstanding: 7000,
      limit: 10000,
      available: 3000,
    });
  });
});
