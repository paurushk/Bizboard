import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useReportPeriod } from '@/utils/useReportPeriod';

beforeEach(() => {
  window.localStorage.clear();
  vi.restoreAllMocks();
});

describe('useReportPeriod', () => {
  it('opens on a bounded preset, not on everything', () => {
    const { result } = renderHook(() => useReportPeriod('t1', 'currentFY'));
    expect(result.current.dateFrom).toMatch(/^\d{4}-04-01$/);
    expect(result.current.dateTo).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(result.current.invalid).toBe(false);
  });

  it('remembers the last valid choice per report', () => {
    const first = renderHook(() => useReportPeriod('t2', 'thisMonth'));
    act(() => first.result.current.setRange({ dateFrom: '2026-04-01', dateTo: '2026-06-30' }));
    first.unmount();
    const second = renderHook(() => useReportPeriod('t2', 'thisMonth'));
    expect(second.result.current.dateFrom).toBe('2026-04-01');
    const other = renderHook(() => useReportPeriod('another', 'thisMonth'));
    expect(other.result.current.dateFrom).not.toBe('2026-04-01');
  });

  it('flags a range that runs backwards and does not remember it', () => {
    const { result } = renderHook(() => useReportPeriod('t3', 'thisMonth'));
    act(() => result.current.setRange({ dateFrom: '2026-08-10', dateTo: '2026-08-01' }));
    expect(result.current.invalid).toBe(true);
    const again = renderHook(() => useReportPeriod('t3', 'thisMonth'));
    expect(again.result.current.invalid).toBe(false);
  });

  it('ignores junk in storage', () => {
    window.localStorage.setItem('bb.reportPeriod.t4', '{"dateFrom":"nope","dateTo":"x"}');
    const { result } = renderHook(() => useReportPeriod('t4', 'thisMonth'));
    expect(result.current.dateFrom).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });

  it('works when storage throws', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    const { result } = renderHook(() => useReportPeriod('t5', 'thisMonth'));
    act(() => result.current.setDateFrom('2026-01-01'));
    expect(result.current.dateFrom).toBe('2026-01-01');
  });

  it('can be cleared by the user (blank dates mean the server default)', () => {
    const { result } = renderHook(() => useReportPeriod('t6', 'thisMonth'));
    act(() => result.current.setRange({ dateFrom: '', dateTo: '' }));
    expect(result.current.invalid).toBe(false);
    expect(result.current.dateFrom).toBe('');
  });
});
