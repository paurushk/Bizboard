import { describe, expect, it } from 'vitest';
import { formatQuantity, parseQuantity, quantityPolicy } from '@/utils/quantity';

describe('quantityPolicy', () => {
  it('keeps whole-unit goods integer and lets measured goods carry decimals', () => {
    expect(quantityPolicy('PCS')).toMatchObject({ decimals: false, min: 1 });
    expect(quantityPolicy('')).toMatchObject({ decimals: false, min: 1 });
    expect(quantityPolicy('kgs')).toMatchObject({ decimals: true, min: 0.001 });
    expect(quantityPolicy('LTR').decimals).toBe(true);
  });
});

describe('parseQuantity', () => {
  const whole = quantityPolicy('PCS');
  const measured = quantityPolicy('KGS');
  it('accepts valid quantities', () => {
    expect(parseQuantity('50', whole)).toBe(50);
    expect(parseQuantity(' 2.5 ', measured)).toBe(2.5);
    expect(parseQuantity('0.0004', measured)).toBeNull(); // rounds below the minimum
    expect(parseQuantity('1.2345', measured)).toBe(1.235);
  });
  it('rejects empty, non-numeric, fractional-for-whole and below-minimum input', () => {
    expect(parseQuantity('', whole)).toBeNull();
    expect(parseQuantity('abc', whole)).toBeNull();
    expect(parseQuantity('2.5', whole)).toBeNull();
    expect(parseQuantity('0', whole)).toBeNull();
    expect(parseQuantity('-3', measured)).toBeNull();
    expect(parseQuantity('0x10', whole)).toBeNull();
    expect(parseQuantity('1e2', whole)).toBeNull();
    expect(parseQuantity('Infinity', measured)).toBeNull();
    expect(parseQuantity('2.', measured)).toBeNull();
  });
  it('formats without trailing noise', () => {
    expect(formatQuantity(2)).toBe('2');
    expect(formatQuantity(2.5)).toBe('2.5');
  });
});
