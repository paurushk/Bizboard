import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useNotices } from './useNotices';

describe('useNotices', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it('a failure replaces a success and a new action clears both', () => {
    const { result } = renderHook(() => useNotices());
    act(() => result.current.success('done'));
    expect(result.current.message).toBe('done');
    act(() => result.current.fail('broke'));
    expect(result.current.message).toBeNull();
    expect(result.current.error).toBe('broke');
    act(() => result.current.clear());
    expect(result.current.error).toBeNull();
  });

  it('a success message dismisses itself but an error stays until cleared', () => {
    const { result } = renderHook(() => useNotices(1000));
    act(() => result.current.success('done'));
    act(() => void vi.advanceTimersByTime(1001));
    expect(result.current.message).toBeNull();
    act(() => result.current.fail('broke'));
    act(() => void vi.advanceTimersByTime(60_000));
    expect(result.current.error).toBe('broke');
  });
});
