import { describe, expect, it } from 'vitest';
import {
  isValidGstin,
  isValidHsnSac,
  isValidIfsc,
  isValidIndianPhone,
  isValidPan,
  isValidPincode,
  isValidUpiVpa,
  normalizeGstRate,
} from '@/utils/gst';

describe('gst utils', () => {
  it('validates GSTIN format and checksum', () => {
    expect(isValidGstin('27AABCU9603R1ZN')).toBe(true);
    expect(isValidGstin('27AABCU9603R1ZM')).toBe(false); // bad checksum
    expect(isValidGstin('invalid')).toBe(false);
    expect(isValidGstin('')).toBe(false);
  });

  it('validates PAN / IFSC / PIN', () => {
    expect(isValidPan('ABCDE1234F')).toBe(true);
    expect(isValidPan('bad')).toBe(false);
    expect(isValidIfsc('HDFC0001234')).toBe(true);
    expect(isValidIfsc('HDFC1001234')).toBe(false);
    expect(isValidPincode('560001')).toBe(true);
    expect(isValidPincode('56001')).toBe(false);
  });

  it('validates HSN/SAC length', () => {
    expect(isValidHsnSac('0401')).toBe(true);
    expect(isValidHsnSac('040110')).toBe(true);
    expect(isValidHsnSac('04011010')).toBe(true);
    expect(isValidHsnSac('12')).toBe(false);
  });

  it('validates UPI VPA format', () => {
    expect(isValidUpiVpa('shop@oksbi')).toBe(true);
    expect(isValidUpiVpa('user.name-1@ybl')).toBe(true);
    expect(isValidUpiVpa('not-a-vpa')).toBe(false);
    expect(isValidUpiVpa('')).toBe(false);
  });

  it('normalizes GST rates to allowed band', () => {
    expect(normalizeGstRate(18)).toBe(18);
    expect(normalizeGstRate(40)).toBe(40);
    expect(normalizeGstRate(99)).toBe(40);
    expect(normalizeGstRate(-1)).toBe(0);
  });

  it('BUG-416: snaps an in-range-but-invalid rate to the nearest real slab', () => {
    expect(normalizeGstRate(15)).toBe(12);
    expect(normalizeGstRate(20)).toBe(18);
    expect(normalizeGstRate(22)).toBe(18);
  });

  it('UXW2B-002: validates Indian mobile numbers', () => {
    expect(isValidIndianPhone('9876543210')).toBe(true);
    expect(isValidIndianPhone('+91 98765 43210')).toBe(true);
    expect(isValidIndianPhone('0-9876543210')).toBe(true);
    expect(isValidIndianPhone('123')).toBe(false);
    expect(isValidIndianPhone('1234567890')).toBe(false); // must start 6-9
    expect(isValidIndianPhone('')).toBe(false);
  });
});
