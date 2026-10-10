import { describe, expect, it } from 'vitest';
import { formatDocumentDate, isOverdueDueDate, todayIsoInTimeZone } from '@/utils/documentDate';

describe('document dates', () => {
  it('formats an ISO date for the register and leaves a blank as a dash', () => {
    expect(formatDocumentDate('2026-10-09')).toMatch(/09/);
    expect(formatDocumentDate('2026-10-09')).toMatch(/2026/);
    expect(formatDocumentDate('')).toBe('—');
  });

  it('uses the calendar date in Asia/Kolkata, including just before midnight UTC', () => {
    // 2026-10-09 18:45 UTC is 10 Oct 00:15 in India.
    const now = new Date('2026-10-09T18:45:00.000Z');
    expect(todayIsoInTimeZone('Asia/Kolkata', now)).toBe('2026-10-10');
    expect(todayIsoInTimeZone('UTC', now)).toBe('2026-10-09');
  });

  it('treats a due date before today as overdue and today as not overdue', () => {
    expect(isOverdueDueDate('2026-10-08', '2026-10-09')).toBe(true);
    expect(isOverdueDueDate('2026-10-09', '2026-10-09')).toBe(false);
    expect(isOverdueDueDate('', '2026-10-09')).toBe(false);
  });
});
