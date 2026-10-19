import { describe, expect, it } from 'vitest';
import { payloadSummary } from '@/pages/reports/statutoryPayload';

describe('payloadSummary', () => {
  it('reads as words, not key=value', () => {
    expect(payloadSummary({ irn: 'abc', ack_no: 123 })).toBe('Irn: abc · Ack No: 123');
  });
  it('leaves out ids, nested objects and empty values', () => {
    expect(payloadSummary({ id: 5, company_id: 9, nested: { a: 1 }, note: '', eway_bill_no: 'E1' })).toBe('Eway Bill No: E1');
  });
  it('shows yes or no for flags and caps at four fields', () => {
    expect(payloadSummary({ a: true, b: false, c: 1, d: 2, e: 3 })).toBe('A: Yes · B: No · C: 1 · D: 2');
  });
  it('is a dash when there is nothing to show', () => {
    expect(payloadSummary(null)).toBe('—');
    expect(payloadSummary({})).toBe('—');
    expect(payloadSummary({ id: 1 })).toBe('—');
  });
});
