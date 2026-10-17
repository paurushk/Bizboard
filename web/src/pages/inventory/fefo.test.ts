import { describe, expect, it } from 'vitest';
import { fefoLot } from '@/pages/inventory/fefo';

describe('fefoLot', () => {
  it('takes the earliest expiry, and lots without an expiry last', () => {
    expect(fefoLot([{ id: 1, expiryDate: null }, { id: 2, expiryDate: '2027-03-01' }, { id: 3, expiryDate: '2026-12-01' }])?.id).toBe(3);
    expect(fefoLot([{ id: 1 }, { id: 2, expiryDate: '2030-01-01' }])?.id).toBe(2);
  });
  it('falls back to the oldest lot when expiries tie, and to null with no lots', () => {
    expect(fefoLot([{ id: 5, expiryDate: '2027-01-01' }, { id: 4, expiryDate: '2027-01-01' }])?.id).toBe(4);
    expect(fefoLot([])).toBeNull();
  });
});
