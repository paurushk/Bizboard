import { describe, expect, it } from 'vitest';
import { showEmpty } from '@/utils/queryState';

describe('showEmpty', () => {
  it('shows only after a successful load with no rows', () => {
    expect(showEmpty({ isLoading: false, isError: false, data: {} }, 0)).toBe(true);
  });
  it('never shows while loading, on error, or before any data', () => {
    expect(showEmpty({ isLoading: true, isError: false, data: {} }, 0)).toBe(false);
    expect(showEmpty({ isLoading: false, isError: true, data: undefined }, 0)).toBe(false);
    expect(showEmpty({ isLoading: false, isError: false, data: undefined }, 0)).toBe(false);
  });
  it('does not trust previous data after a failed refetch', () => {
    expect(showEmpty({ isLoading: false, isError: true, data: { rows: [] } }, 0)).toBe(false);
  });
  it('is false when there are rows', () => {
    expect(showEmpty({ isLoading: false, isError: false, data: {} }, 3)).toBe(false);
  });
});
