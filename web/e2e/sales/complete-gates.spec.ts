/**
 * Complete-gate visibility — sales editor (CG-01, CG-03, CG-05–CG-10).
 */
import { expect, test, type Page } from '@playwright/test';
import {
  assertCompleteEnabled,
  assertDraftEnabledCompleteDisabled,
  fillLineQty,
} from '../complete-gates/assertCompleteGate';
import { loginAsOwner, loginAsOwnerStockBlock } from '../helpers/auth';

async function freshInvoiceEditor(page: Page) {
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
  await page.goto('/sales/new', { waitUntil: 'domcontentloaded' });
  await expect(page.getByRole('heading', { name: /create (sales )?invoice|new invoice/i })).toBeVisible({
    timeout: 15_000,
  });
}

async function addItem(page: Page, query: string, option: RegExp) {
  const productBox = page.getByPlaceholder(/add item|search sku|search product/i);
  await productBox.click();
  await productBox.fill(query);
  await page.getByRole('option', { name: option }).click();
  // This picker adds the line immediately and clears the search box for the
  // next scan — guards against the picked label getting stuck in the box.
  await expect(productBox).toHaveValue('');
}

test.describe('Sales editor — complete gates', () => {
  test('CG-01: GST customer without state/GSTIN disables Complete until state is saved', async ({
    page,
  }) => {
    await loginAsOwner(page);
    await freshInvoiceEditor(page);

    await page.getByRole('combobox', { name: /bill to/i }).fill('No-GST');
    await page.getByRole('option', { name: /No-GST Retail/i }).click();
    await addItem(page, 'Tea', /Premium Tea 500g/i);

    await assertDraftEnabledCompleteDisabled(
      page,
      /customer state or GSTIN/i,
    );

    await page.getByLabel(/^state$/i).selectOption({ label: 'Maharashtra' }).catch(async () => {
      await page.getByLabel(/^state$/i).click();
      await page.getByRole('option', { name: /Maharashtra/i }).click();
    });
    await page.getByRole('button', { name: /^save$/i }).click();
    await assertCompleteEnabled(page);
  });

  test('CG-03: stock BLOCK disables Complete when qty exceeds on-hand', async ({ page }) => {
    await loginAsOwnerStockBlock(page);
    await freshInvoiceEditor(page);

    await page.getByRole('combobox', { name: /bill to/i }).fill('Rahul');
    await page.getByRole('option', { name: /Rahul Stores/i }).click();
    await addItem(page, 'Tea', /Premium Tea 500g/i);

    await fillLineQty(page, '41');
    await assertDraftEnabledCompleteDisabled(page, /Insufficient stock/i);

    await fillLineQty(page, '1');
    await assertCompleteEnabled(page);
  });

  test('CG-05: zero quantity disables Complete', async ({ page }) => {
    await loginAsOwner(page);
    await freshInvoiceEditor(page);
    await page.getByRole('combobox', { name: /bill to/i }).fill('Rahul');
    await page.getByRole('option', { name: /Rahul Stores/i }).click();
    await addItem(page, 'Tea', /Premium Tea 500g/i);

    await fillLineQty(page, '0');
    await assertDraftEnabledCompleteDisabled(page, /quantity greater than zero/i);

    await fillLineQty(page, '1');
    await assertCompleteEnabled(page);
  });

  test('CG-06: sales RCM without confirm disables Complete', async ({ page }) => {
    await loginAsOwner(page);
    await freshInvoiceEditor(page);
    await page.getByRole('combobox', { name: /bill to/i }).fill('Rahul');
    await page.getByRole('option', { name: /Rahul Stores/i }).click();
    await addItem(page, 'Tea', /Premium Tea 500g/i);

    await page.getByRole('button', { name: /advanced tax/i }).click();
    await expect(page.getByRole('checkbox', { name: /sales reverse charge/i })).toBeVisible();
    await page.getByRole('checkbox', { name: /sales reverse charge/i }).check();
    await assertDraftEnabledCompleteDisabled(page, /reverse charge/i);

    await page.getByRole('checkbox', { name: /confirm sales rcm/i }).check();
    await assertCompleteEnabled(page);
  });

  test('CG-07: credit hold disables Complete', async ({ page }) => {
    await loginAsOwner(page);
    await freshInvoiceEditor(page);
    await page.getByRole('combobox', { name: /bill to/i }).fill('Held');
    await page.getByRole('option', { name: /Held Traders/i }).click();
    await addItem(page, 'Tea', /Premium Tea 500g/i);

    await assertDraftEnabledCompleteDisabled(page, /collection hold/i);
  });

  test('CG-08: over credit limit disables Complete', async ({ page }) => {
    await loginAsOwner(page);
    await freshInvoiceEditor(page);
    await page.getByRole('combobox', { name: /bill to/i }).fill('Tight Limit');
    await page.getByRole('option', { name: /Tight Limit Co/i }).click();
    await addItem(page, 'Tea', /Premium Tea 500g/i);

    await assertDraftEnabledCompleteDisabled(page, /credit limit/i);
  });

  test('CG-09: sales serial mismatch disables Complete until serials match qty', async ({
    page,
  }) => {
    await loginAsOwner(page);
    await freshInvoiceEditor(page);
    await page.getByRole('combobox', { name: /bill to/i }).fill('Rahul');
    await page.getByRole('option', { name: /Rahul Stores/i }).click();
    await addItem(page, 'Ampoule', /Serial Ampoule/i);

    await assertDraftEnabledCompleteDisabled(page, /needs serial numbers matching/i);

    await page.getByPlaceholder('SN-001, SN-002').fill('SN-1');
    await assertCompleteEnabled(page);
  });

  test('CG-10: sales batch line left blank still enables Complete (FEFO)', async ({ page }) => {
    await loginAsOwner(page);
    await freshInvoiceEditor(page);
    await page.getByRole('combobox', { name: /bill to/i }).fill('Rahul');
    await page.getByRole('option', { name: /Rahul Stores/i }).click();
    await addItem(page, 'Batch Syrup', /Batch Syrup 50ml/i);

    await assertCompleteEnabled(page);
  });
});
