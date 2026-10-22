import { describe, expect, it } from 'vitest';
import { day, fyStartYear, qty } from './mfgShared';

describe('manufacturing display helpers', () => {
  it('starts the financial year in April, so January to March belong to the year before', () => {
    expect(fyStartYear('2026-03-31')).toBe(2025);
    expect(fyStartYear('2026-04-01')).toBe(2026);
    expect(fyStartYear('2026-12-31')).toBe(2026);
    expect(fyStartYear('2027-01-01')).toBe(2026);
  });

  it('shows a date without a time exactly as written', () => {
    expect(day('2026-10-20')).toMatch(/20/);
    expect(day('2026-10-20')).toMatch(/2026/);
    expect(day(null)).toBe('—');
  });

  it('drops trailing zeros from quantities and keeps a dash for nothing', () => {
    expect(qty('12.500')).toBe('12.5');
    expect(qty('100.000')).toBe('100');
    expect(qty(null)).toBe('—');
  });
});
