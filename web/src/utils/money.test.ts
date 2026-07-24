import { describe, expect, it } from 'vitest';
import { formatMoney, formatNumber, roundMoney } from '@/utils/money';

describe('money utils', () => {
  it('rounds half-up to two decimal places', () => {
    expect(roundMoney(12.345)).toBe(12.35);
    expect(roundMoney(12.344)).toBe(12.34);
    expect(roundMoney(0.905)).toBe(0.91);
    expect(roundMoney(1.809 / 2)).toBe(0.9);
  });

  it('formats INR currency', () => {
    const formatted = formatMoney(5250);
    expect(formatted).toContain('5,250');
  });

  it('formats plain numbers', () => {
    expect(formatNumber(12.5)).toBe('12.50');
  });
});
