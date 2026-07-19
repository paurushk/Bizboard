import { describe, expect, it } from 'vitest';
import { formatMoney, formatNumber, roundMoney } from '@/utils/money';

describe('money utils', () => {
  it('rounds to two decimal places', () => {
    expect(roundMoney(12.345)).toBe(12.35);
    expect(roundMoney(12.344)).toBe(12.34);
  });

  it('formats INR currency', () => {
    const formatted = formatMoney(5250);
    expect(formatted).toContain('5,250');
  });

  it('formats plain numbers', () => {
    expect(formatNumber(12.5)).toBe('12.50');
  });
});
