import { describe, expect, it } from 'vitest';
import { ageSeconds, dayInput, daysFromToday, formatDay, formatSpan, fromLocalInput, plainNumber, toLocalInput } from './format';

describe('care format helpers', () => {
  it('shows a date-only value as the same calendar day', () => {
    expect(formatDay('2026-03-05')).toBe('05 Mar 2026');
    expect(formatDay('2026-12-31T00:00:00Z')).toBe('31 Dec 2026');
    expect(formatDay(null)).toBe('');
    expect(formatDay('not a date')).toBe('');
  });

  it('counts whole days from today, negative once past', () => {
    const now = new Date(2026, 9, 18, 15, 30);
    expect(daysFromToday('2026-10-18', now)).toBe(0);
    expect(daysFromToday('2026-10-25', now)).toBe(7);
    expect(daysFromToday('2026-10-10', now)).toBe(-8);
    expect(daysFromToday('', now)).toBeNull();
  });

  it('writes spans in the largest sensible units', () => {
    expect(formatSpan(45 * 60)).toBe('45m');
    expect(formatSpan(90 * 60)).toBe('1h 30m');
    expect(formatSpan(2 * 3600)).toBe('2h');
    expect(formatSpan(26 * 3600)).toBe('1d 2h');
    expect(formatSpan(-3600)).toBe('1h');
    expect(formatSpan(null)).toBe('');
  });

  it('reads ages and day inputs', () => {
    expect(ageSeconds('2026-10-18T10:00:00Z', Date.parse('2026-10-18T10:01:00Z'))).toBe(60);
    expect(ageSeconds(null)).toBeNull();
    expect(dayInput(0, new Date(2026, 0, 5))).toBe('2026-01-05');
    expect(dayInput(30, new Date(2026, 0, 5))).toBe('2026-02-04');
  });

  it('round-trips a local date-time input', () => {
    const iso = fromLocalInput('2026-10-18T09:30');
    expect(iso).toBeTruthy();
    expect(toLocalInput(iso)).toBe('2026-10-18T09:30');
    expect(fromLocalInput('')).toBeUndefined();
  });

  it('trims trailing zeros from quantities', () => {
    expect(plainNumber('5.000')).toBe('5');
    expect(plainNumber('2.500')).toBe('2.5');
    expect(plainNumber(null)).toBe('');
  });
});
