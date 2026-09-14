import { describe, expect, it } from 'vitest';
import { isCollectionHoldStatus } from '@/utils/collectionHold';

describe('isCollectionHoldStatus', () => {
  it('treats stop_credit and overdue_severe as hold', () => {
    expect(isCollectionHoldStatus('stop_credit')).toBe(true);
    expect(isCollectionHoldStatus('overdue_severe')).toBe(true);
    expect(isCollectionHoldStatus('STOP CREDIT')).toBe(true);
    expect(isCollectionHoldStatus('overdue-severe')).toBe(true);
  });

  it('ignores current / 1-30 overdue buckets', () => {
    expect(isCollectionHoldStatus('open')).toBe(false);
    expect(isCollectionHoldStatus('overdue')).toBe(false);
    expect(isCollectionHoldStatus('')).toBe(false);
    expect(isCollectionHoldStatus(null)).toBe(false);
  });
});
