/**
 * Purchase complete-gates: CG-15 POS, CG-17 serial, CG-19 qty 0, CG-20 company GSTIN.
 */
import { expect, test, type Page } from '@playwright/test';
import {
  assertCompleteEnabled,
  assertDraftEnabledCompleteDisabled,
  fillLineQty,
} from '../complete-gates/assertCompleteGate';
import { loginAsOwner, loginAsOwnerEmptyGstin } from '../helpers/auth';

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

async function addPurchaseItem(page: Page, query: string, option: RegExp) {
  const productBox = page.getByPlaceholder(/add item|search sku|search product/i);
  await productBox.click();
  await productBox.fill(query);
  await page.getByRole('option', { name: option }).click();
  // This picker adds the line immediately and clears the search box for the
  // next scan — guards against the picked label getting stuck in the box.
  await expect(productBox).toHaveValue('');
}

test.describe('Purchase editor — complete gates', () => {
  test('CG-15: GST supplier without state/GSTIN disables Complete', async ({ page }) => {
    await loginAsOwner(page);
    await freshPurchaseEditor(page);

    await page.getByRole('combobox', { name: /bill from/i }).fill('Cash Vendor');
    await page.getByRole('option', { name: /Cash Vendor/i }).click();
    await addPurchaseItem(page, 'Tea', /Premium Tea 500g/i);

    await expect(page.getByText(/supplier state or GSTIN/i).first()).toBeVisible({ timeout: 15_000 });
    await assertDraftEnabledCompleteDisabled(
      page,
      /supplier state or GSTIN/i,
    );

    await page.getByRole('button', { name: /^change$/i }).click();
    await page.getByRole('combobox', { name: /bill from/i }).fill('Western');
    await page.getByRole('option', { name: /Western Distributors/i }).click();
    await assertCompleteEnabled(page);
  });

  test('CG-17: serial-tracked purchase needs serials matching qty', async ({ page }) => {
    await loginAsOwner(page);
    await freshPurchaseEditor(page);
    await page.getByRole('combobox', { name: /bill from/i }).fill('Western');
    await page.getByRole('option', { name: /Western Distributors/i }).click();
    await addPurchaseItem(page, 'Ampoule', /Serial Ampoule/i);

    await assertDraftEnabledCompleteDisabled(page, /needs serial numbers matching/i);

    await page.getByPlaceholder(/SN-001/).fill('SN-1');
    await assertCompleteEnabled(page);
  });

  test('CG-19: purchase qty 0 disables Complete', async ({ page }) => {
    await loginAsOwner(page);
    await freshPurchaseEditor(page);
    await page.getByRole('combobox', { name: /bill from/i }).fill('Western');
    await page.getByRole('option', { name: /Western Distributors/i }).click();
    await addPurchaseItem(page, 'Tea', /Premium Tea 500g/i);

    await fillLineQty(page, '0');
    await assertDraftEnabledCompleteDisabled(page, /quantity greater than zero/i);
    await fillLineQty(page, '1');
    await assertCompleteEnabled(page);
  });

  test('CG-20: empty company GSTIN disables purchase Complete (aligned with sales)', async ({
    page,
  }) => {
    await loginAsOwnerEmptyGstin(page);
    await freshPurchaseEditor(page);
    await page.getByRole('combobox', { name: /bill from/i }).fill('Western');
    await page.getByRole('option', { name: /Western Distributors/i }).click();
    await addPurchaseItem(page, 'Tea', /Premium Tea 500g/i);

    await assertDraftEnabledCompleteDisabled(
      page,
      /Save the company GSTIN in GST settings before completing a GST invoice/i,
    );
  });
});
