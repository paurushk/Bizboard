/**
 * CG-34 orders, CG-35 challan, CG-36 returns — named Complete/Save reasons
 * after party + line are present.
 */
import { expect, test, type Page } from '@playwright/test';
import { fillLineQty } from '../complete-gates/assertCompleteGate';
import { loginAsOwner } from '../helpers/auth';

async function clearDrafts(page: Page) {
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
}

async function addOrderProduct(page: Page, query: string, option: RegExp) {
  const combo = page.getByRole('combobox', { name: 'Products', exact: true });
  await combo.click();
  await combo.fill(query);
  await page.getByRole('option', { name: option }).click();
  // The picked product must actually appear in the box, not the raw typed
  // query — a stale query here looks exactly like the click did nothing.
  await expect(combo).toHaveValue(option);
  await page.getByRole('button', { name: /^add$/i }).click();
}

test.describe('Orders, challans, returns — complete gates', () => {
  test('CG-34: sales order zero qty names the Save reason', async ({ page }) => {
    await loginAsOwner(page);
    await clearDrafts(page);
    await page.goto('/sales/orders/new', { waitUntil: 'domcontentloaded' });
    await expect(page.getByRole('heading', { name: /sales order/i })).toBeVisible({ timeout: 15_000 });

    await page.getByRole('combobox', { name: 'Customer', exact: true }).fill('Rahul');
    await page.getByRole('option', { name: /Rahul Stores/i }).click();
    await addOrderProduct(page, 'Tea', /Premium Tea 500g/i);

    await fillLineQty(page, '0');
    await expect(page.getByRole('button', { name: /^save$/i })).toBeDisabled();
    await expect(page.getByText(/quantity greater than zero/i).first()).toBeVisible();
  });

  test('CG-35: delivery challan zero qty disables Complete with a named reason', async ({ page }) => {
    await loginAsOwner(page);
    await clearDrafts(page);
    await page.goto('/sales/delivery-challans/new', { waitUntil: 'domcontentloaded' });
    await expect(page.getByRole('heading', { name: /delivery challan/i })).toBeVisible({
      timeout: 15_000,
    });

    await page.getByRole('combobox', { name: 'Customer', exact: true }).fill('Rahul');
    await page.getByRole('option', { name: /Rahul Stores/i }).click();
    await addOrderProduct(page, 'Tea', /Premium Tea 500g/i);

    await fillLineQty(page, '0');
    await expect(page.getByRole('button', { name: /save & complete|complete/i }).first()).toBeDisabled();
    await expect(page.getByText(/quantity greater than zero/i).first()).toBeVisible();
  });

  test('CG-36: sales return Complete stays named until a line is selected', async ({ page }) => {
    await loginAsOwner(page);
    await page.goto('/sales/returns', { waitUntil: 'domcontentloaded' });
    await page.getByRole('button', { name: /new sales return/i }).first().click();

    await page.getByLabel(/original invoice/i).click();
    await page.getByRole('option', { name: /INV-2026-0001/i }).click();
    await expect(page.getByText(/Select at least one item to return/i)).toBeVisible();
    await expect(page.getByRole('button', { name: /^complete$/i })).toBeDisabled();

    await page.getByRole('checkbox').first().check();
    await expect(page.getByRole('button', { name: /^complete$/i })).toBeEnabled();
  });

  test('CG-36: purchase return Complete stays named until a line is selected', async ({ page }) => {
    await loginAsOwner(page);
    await page.goto('/purchases/returns', { waitUntil: 'domcontentloaded' });
    await page.getByRole('button', { name: /new purchase return/i }).first().click();

    await page.getByLabel(/original purchase/i).click();
    await page.getByRole('option', { name: /PUR-2026-0001/i }).click();
    await expect(page.getByText(/Select at least one item to return/i)).toBeVisible();
    await expect(page.getByRole('button', { name: /^complete$/i })).toBeDisabled();
  });
});
