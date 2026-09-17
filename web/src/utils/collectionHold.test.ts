import { describe, expect, it } from 'vitest';
import { isCollectionHoldStatus } from '@/utils/collectionHold';

describe('isCollectionHoldStatus — CFT-117 / CFT-118', () => {
  it('holds only stop_credit and overdue_severe', () => {
    expect(isCollectionHoldStatus('stop_credit')).toBe(true);
    expect(isCollectionHoldStatus('overdue_severe')).toBe(true);
    expect(isCollectionHoldStatus('overdue')).toBe(false);
    expect(isCollectionHoldStatus('open')).toBe(false);
    expect(isCollectionHoldStatus(null)).toBe(false);
  });
});
