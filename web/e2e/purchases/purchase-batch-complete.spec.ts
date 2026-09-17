/**
 * CG-16 — Complete-gate visibility (purchase batch).
 *
 * Backend rejects complete without a lot on trackBatch items. The FE already
 * disables Save & Complete for that case — the bug was that party + one line
 * looked sufficient (FEFO / "optional" copy + generic tooltip).
 *
 * Pattern matches gstin-prompt.spec.ts and validation-parity.spec.ts:
 * party + line present → Complete disabled AND a specific visible reason →
 * filling the missing field enables Complete. Draft stays available.
 */
import { expect, test, type Page } from '@playwright/test';
import { assertCompleteEnabled, assertDraftEnabledCompleteDisabled } from '../complete-gates/assertCompleteGate';
import { loginAsOwner } from '../helpers/auth';

async function freshPurchaseEditor(page: Page) {
  await page.goto('/');
  await page.evaluate(() => {
    try {
      for (let i = localStorage.length - 1; i >= 0; i--) {
        const k = localStorage.key(i);
        if (k && (k.includes('outbox') || k.includes('draft'))) {
          localStorage.removeItem(k);
        }
      }
    } catch {
      /* ignore */
    }
  });
  await page.goto('/purchases/new', { waitUntil: 'domcontentloaded' });
  await expect(
    page.getByRole('heading', { name: /create purchase invoice/i }),
  ).toBeVisible({ timeout: 15_000 });
}

test.describe('Purchase editor — batch complete gate', () => {
  test('supplier + tracked item is not enough until a batch number is entered', async ({
    page,
  }) => {
    await loginAsOwner(page);
    await freshPurchaseEditor(page);

    await page.getByRole('combobox', { name: /bill from/i }).fill('Western');
    await page.getByRole('option', { name: /Western Distributors/i }).click();

    const productBox = page.getByPlaceholder(/add item|search sku|search product/i);
    await productBox.click();
    await productBox.fill('Batch Syrup');
    await page.getByRole('option', { name: /Batch Syrup 50ml/i }).click();
    await expect(page.getByText('Batch Syrup 50ml').first()).toBeVisible();
    await expect(productBox).toHaveValue('');

    await expect(page.getByPlaceholder('FEFO batch')).toHaveCount(0);
    await expect(page.getByPlaceholder('New batch no (optional)')).toHaveCount(0);
    await expect(
      page.getByText('Batch Syrup 50ml needs a batch number before Complete'),
    ).toBeVisible();
    await expect(page.getByPlaceholder('Batch number', { exact: true })).toBeVisible();
    await expect(page.getByPlaceholder('New batch number', { exact: true })).toBeVisible();

    await assertDraftEnabledCompleteDisabled(
      page,
      'Batch Syrup 50ml needs a batch number before Complete',
    );

    await page.getByPlaceholder('New batch number').fill('LOT-A');
    await expect(
      page.getByText('Batch Syrup 50ml needs a batch number before Complete'),
    ).toHaveCount(0);
    await assertCompleteEnabled(page);
  });
});
