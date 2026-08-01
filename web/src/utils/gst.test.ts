import { describe, expect, it } from 'vitest';
import { isValidGstin, isValidHsnSac, normalizeGstRate } from '@/utils/gst';

describe('gst utils', () => {
  it('validates GSTIN format', () => {
    expect(isValidGstin('27AABCU9603R1ZM')).toBe(true);
    expect(isValidGstin('invalid')).toBe(false);
    expect(isValidGstin('')).toBe(false);
  });

  it('validates HSN/SAC length', () => {
    expect(isValidHsnSac('0401')).toBe(true);
    expect(isValidHsnSac('040110')).toBe(true);
    expect(isValidHsnSac('04011010')).toBe(true);
    expect(isValidHsnSac('12')).toBe(false);
  });

  it('normalizes GST rates to allowed band', () => {
    expect(normalizeGstRate(18)).toBe(18);
    expect(normalizeGstRate(99)).toBe(28);
    expect(normalizeGstRate(-1)).toBe(0);
  });

  it('BUG-416: snaps an in-range-but-invalid rate to the nearest real slab', () => {
    expect(normalizeGstRate(15)).toBe(12);
    expect(normalizeGstRate(20)).toBe(18);
    expect(normalizeGstRate(22)).toBe(18);
  });
});
