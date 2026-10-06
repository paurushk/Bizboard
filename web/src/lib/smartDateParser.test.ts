import { describe, expect, it } from 'vitest';
import { parseSmartExpiryDate } from '@/lib/smartDateParser';

describe('parseSmartExpiryDate', () => {
  const fixedNow = new Date('2026-09-30T00:00:00Z');

  it('parses 4-digit MMYY to end-of-month', () => {
    const res = parseSmartExpiryDate('0828', { now: fixedNow });
    expect(res.ok).toBe(true);
    if (res.ok) {
      expect(res.dateIso).toBe('2028-08-31');
      expect(res.formatted).toBe('31/08/2028');
      expect(res.preview).toBe('Aug 31, 2028');
    }
  });

  it('parses 4-digit leap year February (0228 -> 2028-02-29)', () => {
    const res = parseSmartExpiryDate('0228', { now: fixedNow });
    expect(res.ok).toBe(true);
    if (res.ok) {
      expect(res.dateIso).toBe('2028-02-29');
    }
  });

  it('parses 6-digit MMYYYY to end-of-month', () => {
    const res = parseSmartExpiryDate('122027', { now: fixedNow });
    expect(res.ok).toBe(true);
    if (res.ok) {
      expect(res.dateIso).toBe('2027-12-31');
      expect(res.preview).toBe('Dec 31, 2027');
    }
  });

  it('parses 8-digit DDMMYYYY to exact day', () => {
    const res = parseSmartExpiryDate('15082028', { now: fixedNow });
    expect(res.ok).toBe(true);
    if (res.ok) {
      expect(res.dateIso).toBe('2028-08-15');
      expect(res.formatted).toBe('15/08/2028');
      expect(res.preview).toBe('Aug 15, 2028');
    }
  });

  it('handles delimiters like MM/YY and DD/MM/YYYY', () => {
    const res1 = parseSmartExpiryDate('08/28', { now: fixedNow });
    expect(res1.ok).toBe(true);
    if (res1.ok) expect(res1.dateIso).toBe('2028-08-31');

    const res2 = parseSmartExpiryDate('25-12-2027', { now: fixedNow });
    expect(res2.ok).toBe(true);
    if (res2.ok) expect(res2.dateIso).toBe('2027-12-25');
  });

  it('rejects dates in the past when allowPast is false (default)', () => {
    const res = parseSmartExpiryDate('0524', { now: fixedNow }); // May 2024
    expect(res.ok).toBe(false);
    if (!res.ok) {
      expect(res.error).toMatch(/cannot be in the past/i);
    }
  });

  it('allows past dates when allowPast is explicitly true (for mfg date)', () => {
    const res = parseSmartExpiryDate('0524', { allowPast: true, now: fixedNow });
    expect(res.ok).toBe(true);
    if (res.ok) {
      expect(res.dateIso).toBe('2024-05-31');
    }
  });

  it('rejects invalid months', () => {
    const res = parseSmartExpiryDate('1328', { now: fixedNow });
    expect(res.ok).toBe(false);
    if (!res.ok) {
      expect(res.error).toMatch(/Month must be between 01 and 12/i);
    }
  });

  it('rejects ambiguous single digits or letters', () => {
    const res1 = parseSmartExpiryDate('3', { now: fixedNow });
    expect(res1.ok).toBe(false);

    const res2 = parseSmartExpiryDate('invalid', { now: fixedNow });
    expect(res2.ok).toBe(false);
  });

  it('uses the local calendar day, not the UTC date', () => {
    const earlyMorning = new Date(2026, 8, 30, 1, 0, 0);
    const yesterday = parseSmartExpiryDate('29092026', { now: earlyMorning });
    expect(yesterday.ok).toBe(false);
    if (!yesterday.ok) expect(yesterday.code).toBe('past');

    const today = parseSmartExpiryDate('30092026', { now: earlyMorning });
    expect(today.ok).toBe(true);
  });
});
