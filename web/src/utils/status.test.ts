import { describe, expect, it } from 'vitest';
import { documentStatusTone, paidAwareStatus, statusLabelKey } from './status';

describe('paidAwareStatus', () => {
  it('maps a completed zero-balance invoice to PAID', () => {
    expect(paidAwareStatus('COMPLETED', 0)).toBe('PAID');
    expect(paidAwareStatus('COMPLETED', '0.00')).toBe('PAID');
    expect(statusLabelKey(paidAwareStatus('COMPLETED', 0))).toBe('status.PAID');
    expect(documentStatusTone('PAID')).toBe('success');
  });

  it('keeps completed when a balance remains', () => {
    expect(paidAwareStatus('COMPLETED', 10)).toBe('COMPLETED');
  });

  it('does not treat missing balance as paid', () => {
    expect(paidAwareStatus('COMPLETED')).toBe('COMPLETED');
    expect(paidAwareStatus('COMPLETED', null)).toBe('COMPLETED');
  });

  it('maps gateway holding to paid-pending-books', () => {
    expect(paidAwareStatus('COMPLETED', 1000, 'PAID_PENDING_BOOKS')).toBe('PAID_PENDING_BOOKS');
    expect(statusLabelKey(paidAwareStatus('COMPLETED', 1000, 'PAID_PENDING_BOOKS'))).toBe(
      'status.PAID_PENDING_BOOKS',
    );
    expect(documentStatusTone('PAID_PENDING_BOOKS')).toBe('info');
  });
});
