import 'fake-indexeddb/auto';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ACTIVE_COMPANY_STORAGE_KEY } from '@/api/client';
import { companyChangedFrom, installCompanySwitchListener } from '@/api/companyContext';
import { flushReceiptOutbox, listQueuedReceipts, queueReceipt, removeQueuedReceipt } from '@/offline/receiptOutbox';
import { flushPosBatch, flushPosDraft } from '@/offline/flushPosCheckout';
import type { OutboxDraft } from '@/offline/invoiceDraftCache';

afterEach(() => localStorage.removeItem(ACTIVE_COMPANY_STORAGE_KEY));

function fireStorage(oldValue: string | null, newValue: string | null) {
  window.dispatchEvent(new StorageEvent('storage', { key: ACTIVE_COMPANY_STORAGE_KEY, oldValue, newValue }));
}

describe('WP-ID2 company context', () => {
  it('reloads this tab when another tab switches company, but not on a first pick', () => {
    const reload = vi.fn();
    const uninstall = installCompanySwitchListener(reload);
    fireStorage(null, '7'); // first selection on a fresh device
    expect(reload).not.toHaveBeenCalled();
    fireStorage('7', '8');
    expect(reload).toHaveBeenCalledTimes(1);
    uninstall();
  });

  it('reloads when another tab clears the company and then sets a new one', () => {
    localStorage.setItem(ACTIVE_COMPANY_STORAGE_KEY, '7');
    const reload = vi.fn();
    const uninstall = installCompanySwitchListener(reload);
    fireStorage('7', null); // a 409 conflict in another tab removes the key first
    expect(reload).toHaveBeenCalledTimes(1);
    uninstall();
  });

  it('treats nothing stored as no switch, and a different id as a switch', () => {
    expect(companyChangedFrom(7)).toBe(false);
    localStorage.setItem(ACTIVE_COMPANY_STORAGE_KEY, '7');
    expect(companyChangedFrom(7)).toBe(false);
    localStorage.setItem(ACTIVE_COMPANY_STORAGE_KEY, '8');
    expect(companyChangedFrom(7)).toBe(true);
  });

  it('stops flushing receipts once the company changed, leaving them queued', async () => {
    const company = 7;
    const user = 3;
    for (const row of await listQueuedReceipts(company, user)) await removeQueuedReceipt(row.id);
    for (const id of ['c1', 'c2']) {
      await queueReceipt({
        id,
        companyId: company,
        userId: user,
        customerName: 'Ravi',
        payload: { customer: 1, amount: 100, mode: 'CASH', receiptDate: '2026-10-09' },
      } as Parameters<typeof queueReceipt>[0]);
    }
    localStorage.setItem(ACTIVE_COMPANY_STORAGE_KEY, '7');
    const send = vi.fn().mockImplementation(async () => {
      // The user switches to company 8 in another tab while the first receipt is in flight.
      localStorage.setItem(ACTIVE_COMPANY_STORAGE_KEY, '8');
    });
    const result = await flushReceiptOutbox(company, user, send);
    expect(send).toHaveBeenCalledTimes(1);
    expect(result.sent).toBe(1);
    expect(result.remaining).toBe(1);
  });

  it('refuses to post POS drafts of another company, before writing anything', async () => {
    localStorage.setItem(ACTIVE_COMPANY_STORAGE_KEY, '8');
    const draft = { companyId: 7, userId: 3, idempotencyKey: 'k', payload: {}, lines: [] } as unknown as OutboxDraft;
    await expect(flushPosDraft(draft)).rejects.toThrow(/Company changed/);
    await expect(flushPosBatch([draft])).rejects.toThrow(/Company changed/);
  });
});
