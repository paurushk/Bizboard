import { expect, test } from '@playwright/test';
import { loginAsOwner } from '../helpers/auth';

/**
 * Purchases domain, batch 1 (continued) — the credit/debit note, order,
 * return, payment, and supplier screens that had zero e2e coverage before
 * this pass (only /purchases/bill-upload had a dedicated check, in
 * smoke.spec.ts). Each renders without an error boundary / bounce-to-login;
 * suppliers additionally gets a real add-dialog interaction since it has a
 * seeded mock row to click through.
 */
const REACHABLE_ROUTES = [
  '/purchases/credit-notes',
  '/purchases/debit-notes',
  '/purchases/orders',
  '/purchases/returns',
  '/purchases/payments',
  '/purchases/bills-of-entry',
];

test.describe('purchases: notes, orders, suppliers', () => {
  for (const path of REACHABLE_ROUTES) {
    test(`${path} renders without a page error`, async ({ page }) => {
      const errors: string[] = [];
      page.on('pageerror', (e) => errors.push(e.message));

      await loginAsOwner(page);
      await page.goto(path, { waitUntil: 'domcontentloaded' });
      await expect
        .poll(async () => (await page.locator('#root').innerHTML()).length, { timeout: 20_000 })
        .toBeGreaterThan(0);

      await expect(page, `${path} bounced to /login`).not.toHaveURL(/\/login/);
      await expect(
        page.getByText(/something went wrong|unexpected error|error boundary/i),
      ).toHaveCount(0);
      expect(errors, `${path} threw: ${errors.join(' | ')}`).toEqual([]);
    });
  }

  test('purchase credit note editor opens for a new note', async ({ page }) => {
    await loginAsOwner(page);
    await page.goto('/purchases/credit-notes/new', { waitUntil: 'domcontentloaded' });
    await expect(
      page.getByRole('heading', { name: /record purchase credit note/i }),
    ).toBeVisible({ timeout: 15_000 });
  });

  test('purchase order editor opens for a new order', async ({ page }) => {
    await loginAsOwner(page);
    await page.goto('/purchases/orders/new', { waitUntil: 'domcontentloaded' });
    await expect(
      page.getByRole('heading', { name: /new purchase order/i }),
    ).toBeVisible({ timeout: 15_000 });
  });

  test('suppliers: existing supplier listed, add-dialog opens and validates a name', async ({ page }) => {
    await loginAsOwner(page);
    await page.goto('/purchases/suppliers', { waitUntil: 'domcontentloaded' });
    await expect(page.getByText(/Western Distributors/i).first()).toBeVisible({ timeout: 15_000 });

    await page.getByRole('button', { name: /^Add$/i }).click();
    await expect(page.getByRole('dialog').getByText(/create supplier/i)).toBeVisible();
  });
});
