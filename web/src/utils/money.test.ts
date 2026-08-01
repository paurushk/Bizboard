import { describe, expect, it } from 'vitest';
import { formatMoney, formatNumber, roundMoney, toNumber } from '@/utils/money';

describe('money utils', () => {
  it('rounds half-up to two decimal places', () => {
    expect(roundMoney(12.345)).toBe(12.35);
    expect(roundMoney(12.344)).toBe(12.34);
    expect(roundMoney(0.905)).toBe(0.91);
    expect(roundMoney(1.809 / 2)).toBe(0.9);
  });

  it('rounds negative amounts half-up on the magnitude', () => {
    expect(roundMoney(-12.345)).toBe(-12.35);
    expect(roundMoney(-0.005)).toBe(-0.01);
  });

  it('does not mis-round float-representation edge cases (BUG-201/400)', () => {
    // 6 * 853.65 * 0.05 = 256.095 exactly in decimal; float64 multiplication
    // can land a hair either side of the .5 boundary, which the previous
    // scale-by-100-plus-epsilon implementation sometimes got wrong.
    expect(roundMoney(6 * 853.65 * 0.05)).toBe(256.1);
    expect(roundMoney(5 * 1030.1 * 0.09)).toBe(463.55);
  });

  it('formats INR currency', () => {
    const formatted = formatMoney(5250);
    expect(formatted).toContain('5,250');
  });

  it('formats plain numbers', () => {
    expect(formatNumber(12.5)).toBe('12.50');
  });

  it('coerces malformed input to 0 rather than throwing', () => {
    expect(toNumber('abc')).toBe(0);
    expect(toNumber(null)).toBe(0);
    expect(toNumber(undefined)).toBe(0);
  });
});
