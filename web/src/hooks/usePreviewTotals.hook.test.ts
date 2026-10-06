import { renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { usePreviewTotals } from '@/hooks/usePreviewTotals';

const api = vi.hoisted(() => ({
  previewSalesTotals: vi.fn(),
  previewPurchaseTotals: vi.fn(),
}));

vi.mock('@/api/resources', () => ({
  previewSalesTotals: api.previewSalesTotals,
  previewPurchaseTotals: api.previewPurchaseTotals,
}));

const TOTALS = { grandTotal: 118, taxTotal: 18 };

describe('usePreviewTotals', () => {
  beforeEach(() => {
    api.previewSalesTotals.mockReset();
    api.previewPurchaseTotals.mockReset();
  });

  it('does nothing without a body', () => {
    const { result } = renderHook(() => usePreviewTotals('sales', null));
    expect(result.current).toEqual({ totals: null, error: null, pending: false, ready: false });
    expect(api.previewSalesTotals).not.toHaveBeenCalled();
  });

  it('shows pending, then the totals, then ready', async () => {
    api.previewSalesTotals.mockResolvedValue(TOTALS);
    const { result } = renderHook(() => usePreviewTotals('sales', { items: [1] }));
    expect(result.current.pending).toBe(true);
    expect(result.current.ready).toBe(false);
    await waitFor(() => expect(result.current.ready).toBe(true));
    expect(result.current.totals).toEqual(TOTALS);
    expect(result.current.pending).toBe(false);
    expect(api.previewSalesTotals).toHaveBeenCalledWith({ items: [1] });
  });

  it('uses the purchase preview for purchase documents', async () => {
    api.previewPurchaseTotals.mockResolvedValue(TOTALS);
    const { result } = renderHook(() => usePreviewTotals('purchase', { items: [2] }));
    await waitFor(() => expect(result.current.ready).toBe(true));
    expect(api.previewPurchaseTotals).toHaveBeenCalledTimes(1);
    expect(api.previewSalesTotals).not.toHaveBeenCalled();
  });

  it('reports an error and is never ready when the preview fails', async () => {
    api.previewSalesTotals.mockRejectedValue(new Error('Preview is down'));
    const { result } = renderHook(() => usePreviewTotals('sales', { items: [1] }));
    await waitFor(() => expect(result.current.error).toBe('Preview is down'));
    expect(result.current.totals).toBeNull();
    expect(result.current.ready).toBe(false);
    expect(result.current.pending).toBe(false);
  });

  it('clears the last totals when the body is emptied', async () => {
    api.previewSalesTotals.mockResolvedValue(TOTALS);
    const { result, rerender } = renderHook(
      ({ body }: { body: Record<string, unknown> | null }) => usePreviewTotals('sales', body),
      { initialProps: { body: { items: [1] } as Record<string, unknown> | null } },
    );
    await waitFor(() => expect(result.current.ready).toBe(true));

    rerender({ body: null });
    await waitFor(() => expect(result.current.totals).toBeNull());
    expect(result.current.ready).toBe(false);
    expect(result.current.pending).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it('is not ready while a changed body is being previewed', async () => {
    api.previewSalesTotals.mockResolvedValueOnce(TOTALS);
    let release: (value: unknown) => void = () => {};
    api.previewSalesTotals.mockImplementationOnce(() => new Promise((resolve) => { release = resolve; }));
    const { result, rerender } = renderHook(
      ({ body }: { body: Record<string, unknown> | null }) => usePreviewTotals('sales', body),
      { initialProps: { body: { items: [1] } as Record<string, unknown> | null } },
    );
    await waitFor(() => expect(result.current.ready).toBe(true));

    rerender({ body: { items: [1, 2] } });
    await waitFor(() => expect(result.current.pending).toBe(true));
    expect(result.current.ready).toBe(false);

    release({ grandTotal: 236, taxTotal: 36 });
    await waitFor(() => expect(result.current.ready).toBe(true));
    expect(result.current.totals).toEqual({ grandTotal: 236, taxTotal: 36 });
  });
});
