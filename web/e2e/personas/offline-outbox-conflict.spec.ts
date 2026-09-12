/**
 * §H1 — the offline draft outbox distinguishes a draft that is queued to sync
 * from one the server rejected (a conflict: closed period, stale invoice, …).
 * A rejected draft does NOT auto-retry (SR-51 / `isFlushableDraft`); the operator
 * must edit-and-resend or discard it, and the row must say so.
 *
 * Drafts live in `localStorage['bizboard:invoice-outbox:v2:<companyId>:<userId>']`
 * as a JSON array of OutboxDraft (see src/offline/invoiceDraftCache.ts). The mock
 * owner is companyId=1 / userId=1.
 */
import { expect, test } from '@playwright/test';
import { loginAsOwner } from '../helpers/auth';

const OUTBOX_KEY = 'bizboard:invoice-outbox:v2:1:1';

function draft(over: Record<string, unknown>) {
  return {
    version: 2,
    companyId: 1,
    userId: 1,
    kind: 'invoice',
    savedAt: '2026-06-10T09:00:00.000Z',
    payload: { customer: 1, items: [{ product: 1, quantity: 2, unitPrice: 100 }] },
    invoiceId: null,
    customerId: 1,
    lines: [{ product: 1, quantity: 2, unitPrice: 100 }],
    completeIntent: true,
    conflict: null,
    ...over,
  };
}

test.describe('§H1 — offline outbox: queued vs conflicted', () => {
  test('a queued draft and a server-rejected draft render with distinct status', async ({ page }) => {
    await loginAsOwner(page);

    const queued = draft({ id: '1:1:queued-1', idempotencyKey: 'queued-1' });
    const rejected = draft({
      id: '1:1:rejected-1',
      idempotencyKey: 'rejected-1',
      conflict: { code: 'closed_period', message: 'This period is closed; complete it in an open period.' },
    });

    await page.goto('/');
    await page.evaluate(
      ([key, rows]) => localStorage.setItem(key, JSON.stringify(rows)),
      [OUTBOX_KEY, [queued, rejected]] as const,
    );

    await page.goto('/offline-outbox');
    await expect(page.getByRole('heading', { name: /offline outbox/i })).toBeVisible({
      timeout: 15_000,
    });

    // both drafts listed, by their id
    await expect(page.getByText('1:1:queued-1')).toBeVisible();
    await expect(page.getByText('1:1:rejected-1')).toBeVisible();

    // the queued one is flushable
    await expect(page.getByText(/queued to sync/i)).toBeVisible();
    // the rejected one is parked with the server's reason — not "queued"
    await expect(page.getByText(/rejected: this period is closed/i)).toBeVisible();

    // "Sync now" is available (the browser reports online in a normal run)
    await expect(page.getByRole('button', { name: /sync now/i })).toBeEnabled();
  });

  test('discarding a conflicted draft asks for confirmation first', async ({ page }) => {
    await loginAsOwner(page);
    const rejected = draft({
      id: '1:1:rejected-2',
      idempotencyKey: 'rejected-2',
      conflict: { code: 'stale_invoice', message: 'This invoice changed on the server.' },
    });
    await page.goto('/');
    await page.evaluate(
      ([key, rows]) => localStorage.setItem(key, JSON.stringify(rows)),
      [OUTBOX_KEY, [rejected]] as const,
    );
    await page.goto('/offline-outbox');
    await expect(page.getByText('1:1:rejected-2')).toBeVisible({ timeout: 15_000 });

    await page.getByRole('button', { name: /^delete$/i }).click();
    // a confirm dialog, not an immediate delete — the row is still there behind it
    await expect(page.getByRole('dialog')).toBeVisible();
    await expect(page.getByText('1:1:rejected-2')).toBeVisible();
  });
});
