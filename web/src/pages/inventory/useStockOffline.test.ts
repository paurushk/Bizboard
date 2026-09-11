import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushOutbox, listDrafts } from '@/offline/invoiceDraftCache';
import { useStockOffline } from '@/pages/inventory/useStockOffline';

vi.mock('@/offline/invoiceDraftCache', () => ({
  listDrafts: vi.fn(),
  flushOutbox: vi.fn(),
  removeDraft: vi.fn(),
}));

vi.mock('@/api/resources', () => ({
  completeTransfer: vi.fn(),
  postStockCount: vi.fn(),
  updateStockCount: vi.fn(),
}));

vi.mock('@/i18n', () => ({
  t: (key: string) => key,
}));

describe('useStockOffline (R-047)', () => {
  beforeEach(() => {
    vi.mocked(listDrafts).mockResolvedValue([]);
    vi.mocked(flushOutbox).mockResolvedValue({ flushed: 0, failed: 0, conflicts: 0, errors: [] });
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: true });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('flushes stock drafts on mount and again on the online event', async () => {
    renderHook(() => useStockOffline(1, 9));
    await act(async () => {
      await Promise.resolve();
    });
    expect(flushOutbox).toHaveBeenCalledTimes(1);

    await act(async () => {
      window.dispatchEvent(new Event('online'));
      await Promise.resolve();
    });
    expect(flushOutbox).toHaveBeenCalledTimes(2);
    expect(flushOutbox).toHaveBeenCalledWith(
      1,
      9,
      expect.any(Function),
      expect.any(Function),
    );
  });

  it('does not flush while the browser is offline', async () => {
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: false });
    renderHook(() => useStockOffline(1, 9));
    await act(async () => {
      await Promise.resolve();
    });
    expect(flushOutbox).not.toHaveBeenCalled();
  });
});

describe('flushStockDraft conflict event (CR-143)', () => {
  it('dispatches STOCK_COUNT_CONFLICT_EVENT on 409', async () => {
    const { flushStockDraft, STOCK_COUNT_CONFLICT_EVENT } = await import(
      '@/pages/inventory/useStockOffline'
    );
    const { postStockCount } = await import('@/api/resources');
    const err = {
      response: {
        status: 409,
        data: {
          error: {
            code: 'STOCK_COUNT_CONFLICT',
            details: {
              conflicts: [
                {
                  lineId: 1,
                  productName: 'Widget',
                  serverQty: '5',
                  localQty: '4',
                  snapshotQty: '5',
                },
              ],
            },
          },
        },
      },
    };
    vi.mocked(postStockCount).mockRejectedValueOnce(err);
    const seen: unknown[] = [];
    const handler = (e: Event) => seen.push((e as CustomEvent).detail);
    window.addEventListener(STOCK_COUNT_CONFLICT_EVENT, handler);
    await expect(
      flushStockDraft(
        {
          kind: 'stock_count',
          payload: { sessionId: 44, lines: {} },
          idempotencyKey: 'sc-44',
        } as never,
        { companyId: 1, userId: 9 },
      ),
    ).rejects.toBe(err);
    window.removeEventListener(STOCK_COUNT_CONFLICT_EVENT, handler);
    expect(seen).toHaveLength(1);
    expect(seen[0]).toMatchObject({ sessionId: 44, companyId: 1, userId: 9 });
  });
});
