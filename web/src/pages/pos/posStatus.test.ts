import { describe, expect, it } from 'vitest';
import { posChipState, unpaidRecoverFromAbort } from './posStatus';

describe('posChipState (A-04)', () => {
  it('is Unsaved when the cart is local-only and online', () => {
    expect(posChipState({ cartCount: 2, hasOutbox: false, offline: false, justCompleted: false })).toBe(
      'unsaved',
    );
  });

  it('is Offline queued when the outbox has items or the cart is held offline', () => {
    expect(posChipState({ cartCount: 1, hasOutbox: true, offline: true, justCompleted: false })).toBe(
      'offline',
    );
    expect(posChipState({ cartCount: 1, hasOutbox: false, offline: true, justCompleted: false })).toBe(
      'offline',
    );
  });

  it('is Saved draft when queued drafts exist and the device is online', () => {
    expect(posChipState({ cartCount: 0, hasOutbox: true, offline: false, justCompleted: false })).toBe(
      'saved',
    );
  });

  it('is Completed after a posted sale with an empty cart', () => {
    expect(posChipState({ cartCount: 0, hasOutbox: false, offline: false, justCompleted: true })).toBe(
      'completed',
    );
  });
});

describe('unpaidRecoverFromAbort (A-04)', () => {
  it('returns a recover CTA target when an unpaid invoice id is present', () => {
    expect(
      unpaidRecoverFromAbort({ invoiceId: 44, invoiceNumber: 'POS-12' }),
    ).toEqual({ id: 44, number: 'POS-12' });
  });

  it('is null when UPI never created an invoice', () => {
    expect(unpaidRecoverFromAbort(null)).toBeNull();
  });
});
