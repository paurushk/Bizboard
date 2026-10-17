import { renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  requestStockFlush,
  STOCK_FLUSHED_EVENT,
  useStockOffline,
} from '@/pages/inventory/useStockOffline';

const postStockCount = vi.hoisted(() => vi.fn());
const updateStockCount = vi.hoisted(() => vi.fn());
const completeTransfer = vi.hoisted(() => vi.fn());
const listDrafts = vi.hoisted(() => vi.fn());
const removeDraft = vi.hoisted(() => vi.fn());
const flushOutbox = vi.hoisted(() => vi.fn());

vi.mock('@/api/resources', () => ({
  postStockCount: (...a: unknown[]) => postStockCount(...a),
  updateStockCount: (...a: unknown[]) => updateStockCount(...a),
  completeTransfer: (...a: unknown[]) => completeTransfer(...a),
}));
vi.mock('@/offline/invoiceDraftCache', () => ({
  listDrafts: (...a: unknown[]) => listDrafts(...a),
  removeDraft: (...a: unknown[]) => removeDraft(...a),
  flushOutbox: (...a: unknown[]) => flushOutbox(...a),
}));

const countDraft = {
  id: 'd1', kind: 'stock_count', idempotencyKey: 'stock-count-5', companyId: 1, userId: 2,
  payload: { sessionId: 5, lines: { '11': '4' }, resolveConflicts: '' },
};

describe('useStockOffline', () => {
  beforeEach(() => {
    for (const fn of [postStockCount, updateStockCount, completeTransfer, listDrafts, removeDraft, flushOutbox]) fn.mockReset();
    removeDraft.mockResolvedValue(undefined);
    updateStockCount.mockResolvedValue({});
    flushOutbox.mockResolvedValue({ flushed: 0, failed: 0, conflicts: 0, errors: [], failedDrafts: [] });
  });

  it('sends a queued count, removes it and tells open lists to refetch', async () => {
    listDrafts.mockResolvedValueOnce([countDraft]).mockResolvedValue([]);
    postStockCount.mockResolvedValue({});
    const flushed = vi.fn();
    window.addEventListener(STOCK_FLUSHED_EVENT, flushed);
    const banner = vi.fn();
    renderHook(() => useStockOffline(1, 2, banner));
    await waitFor(() => expect(postStockCount).toHaveBeenCalledWith(5, {}, { idempotencyKey: 'stock-count-5' }));
    await waitFor(() => expect(removeDraft).toHaveBeenCalledWith(1, 2, 'stock-count-5'));
    await waitFor(() => expect(flushed).toHaveBeenCalled());
    window.removeEventListener(STOCK_FLUSHED_EVENT, flushed);
  });

  it('tells the user a sent count is waiting for the owner instead of leaving it silent', async () => {
    listDrafts.mockResolvedValueOnce([countDraft]).mockResolvedValue([]);
    postStockCount.mockResolvedValue({ status: 'PENDING', approvalId: 3 });
    const banner = vi.fn();
    renderHook(() => useStockOffline(1, 2, banner));
    await waitFor(() => expect(removeDraft).toHaveBeenCalledWith(1, 2, 'stock-count-5'));
    await waitFor(() => expect(banner.mock.calls.some(([m]) => String(m).includes('waiting for the owner'))).toBe(true));
  });

  it('keeps a failed count queued and reports the failure to the caller', async () => {
    listDrafts.mockResolvedValue([countDraft]);
    postStockCount.mockRejectedValue(new Error('Server said no'));
    const banner = vi.fn();
    renderHook(() => useStockOffline(1, 2, banner));
    await waitFor(() => expect(banner.mock.calls.some(([m]) => String(m).includes('Server said no'))).toBe(true));
    expect(removeDraft).not.toHaveBeenCalled();
  });

  it('does a second pass when a page asks for one', async () => {
    listDrafts.mockResolvedValue([]);
    renderHook(() => useStockOffline(1, 2));
    // One pass reads the queue more than once, so compare before and after the request.
    await waitFor(() => expect(listDrafts).toHaveBeenCalled());
    await new Promise((r) => setTimeout(r, 50));
    const before = listDrafts.mock.calls.length;
    requestStockFlush();
    await waitFor(() => expect(listDrafts.mock.calls.length).toBeGreaterThan(before));
  });

  it('does nothing before sign-in', async () => {
    renderHook(() => useStockOffline(0, 0));
    await new Promise((r) => setTimeout(r, 20));
    expect(listDrafts).not.toHaveBeenCalled();
  });
});
