import { act, renderHook } from '@testing-library/react';
import { AxiosError, type InternalAxiosRequestConfig } from 'axios';
import { describe, expect, it, vi } from 'vitest';
import { useSettingsForm } from './useSettingsForm';

type Values = { prefix: string };

function axiosError(status: number, data: unknown = {}) {
  return new AxiosError('failed', String(status), undefined, undefined, {
    status,
    statusText: '',
    data,
    headers: {},
    config: {} as InternalAxiosRequestConfig,
  });
}

describe('useSettingsForm', () => {
  it('is clean until a value changes, and discard restores the saved values', () => {
    const save = vi.fn();
    const { result } = renderHook(() => useSettingsForm<Values, { updatedAt?: string }>({ initial: { prefix: 'INV' }, save }));
    expect(result.current.dirty).toBe(false);
    act(() => result.current.setValues({ prefix: 'SAL' }));
    expect(result.current.dirty).toBe(true);
    act(() => result.current.discard());
    expect(result.current.values.prefix).toBe('INV');
    expect(result.current.dirty).toBe(false);
  });

  it('sends one idempotency key and the expected updatedAt, then becomes clean', async () => {
    const save = vi.fn().mockResolvedValue({ updatedAt: '2026-10-19T10:00:00Z' });
    const { result } = renderHook(() =>
      useSettingsForm<Values, { updatedAt?: string }>({ initial: { prefix: 'INV' }, initialUpdatedAt: '2026-10-18T10:00:00Z', save }),
    );
    act(() => result.current.setValues({ prefix: 'SAL' }));
    await act(async () => {
      await result.current.save();
    });
    const ctx = save.mock.calls[0][1];
    expect(ctx.headers['Idempotency-Key']).toBeTruthy();
    expect(ctx.expectedUpdatedAt).toBe('2026-10-18T10:00:00Z');
    expect(result.current.dirty).toBe(false);
    act(() => result.current.setValues({ prefix: 'NEW' }));
    await act(async () => {
      await result.current.save();
    });
    expect(save.mock.calls[1][1].expectedUpdatedAt).toBe('2026-10-19T10:00:00Z');
    expect(save.mock.calls[1][1].headers['Idempotency-Key']).not.toBe(ctx.headers['Idempotency-Key']);
  });

  it('keeps the same key when the connection drops, so a retry is one operation', async () => {
    const save = vi
      .fn()
      .mockRejectedValueOnce(new AxiosError('Network Error'))
      .mockResolvedValueOnce({ updatedAt: 'x' });
    const { result } = renderHook(() => useSettingsForm<Values, { updatedAt?: string }>({ initial: { prefix: 'INV' }, save }));
    act(() => result.current.setValues({ prefix: 'SAL' }));
    await act(async () => {
      await result.current.save();
    });
    expect(result.current.error).toBeTruthy();
    await act(async () => {
      await result.current.save();
    });
    expect(save.mock.calls[1][1].headers['Idempotency-Key']).toBe(save.mock.calls[0][1].headers['Idempotency-Key']);
  });

  it('opens a conflict on 409 and overwrite resends without expectedUpdatedAt', async () => {
    const save = vi
      .fn()
      .mockRejectedValueOnce(axiosError(409, { current: 1 }))
      .mockResolvedValueOnce({ updatedAt: 'new' });
    const { result } = renderHook(() =>
      useSettingsForm<Values, { updatedAt?: string }>({ initial: { prefix: 'INV' }, initialUpdatedAt: 'old', save }),
    );
    act(() => result.current.setValues({ prefix: 'SAL' }));
    await act(async () => {
      await result.current.save();
    });
    expect(result.current.conflict).not.toBeNull();
    await act(async () => {
      await result.current.resolveConflict('overwrite');
    });
    expect(save.mock.calls[1][1].expectedUpdatedAt).toBeNull();
    expect(result.current.conflict).toBeNull();
    expect(result.current.dirty).toBe(false);
  });

  it('reload after a conflict takes the latest server values', async () => {
    const save = vi.fn().mockRejectedValueOnce(axiosError(409));
    const refetch = vi.fn().mockResolvedValue({ values: { prefix: 'SERVER' }, updatedAt: 'fresh' });
    const { result } = renderHook(() =>
      useSettingsForm<Values, { updatedAt?: string }>({ initial: { prefix: 'INV' }, save, refetch }),
    );
    act(() => result.current.setValues({ prefix: 'SAL' }));
    await act(async () => {
      await result.current.save();
    });
    await act(async () => {
      await result.current.resolveConflict('reload');
    });
    expect(result.current.values.prefix).toBe('SERVER');
    expect(result.current.dirty).toBe(false);
  });

  it('ignores a second save while one is in flight', async () => {
    let release: (v: { updatedAt?: string }) => void = () => undefined;
    const save = vi.fn().mockImplementation(
      () => new Promise<{ updatedAt?: string }>((resolve) => { release = resolve; }),
    );
    const { result } = renderHook(() => useSettingsForm<Values, { updatedAt?: string }>({ initial: { prefix: 'INV' }, save }));
    act(() => result.current.setValues({ prefix: 'SAL' }));
    let first: Promise<unknown> = Promise.resolve();
    await act(async () => {
      first = result.current.save();
      void result.current.save();
    });
    expect(save).toHaveBeenCalledTimes(1);
    await act(async () => {
      release({});
      await first;
    });
  });
});
