/**
 * POS pay gates CG-28–CG-31 (cart has items; pay still blocked with a named reason).
 */
import { expect, test, type Page } from '@playwright/test';
import { fillLineQty } from '../complete-gates/assertCompleteGate';
import { loginAsOwner, loginAsOwnerStockBlock } from '../helpers/auth';

/** The full-amount cash button. The split-tender button also matches /cash/ and stays disabled at ₹0. */
function cashPay(page: Page) {
  return page.getByRole('button', { name: /^Cash\s+[—-]/ });
}

async function openPos(page: Page) {
  await page.goto('/pos', { waitUntil: 'domcontentloaded' });
  await expect(page.getByRole('heading', { name: /pos|point of sale|counter/i })).toBeVisible({
    timeout: 15_000,
  });
}

async function addPosItem(page: Page, query: string, option: RegExp) {
  const box = page.getByPlaceholder(/scan barcode/i);
  await box.click();
  await box.fill(query);
  const opt = page.getByRole('option', { name: option });
  await expect(opt).toBeVisible({ timeout: 15_000 });
  await opt.click();
  // POS adds the line immediately and clears the box for the next scan —
  // guards against the picked label getting stuck in the box.
  await expect(box).toHaveValue('');
}

test.describe('POS — complete/pay gates', () => {
  test('CG-29: batch-tracked cart line disables pay until a lot is entered', async ({ page }) => {
    await loginAsOwner(page);
    await openPos(page);
    await addPosItem(page, 'Batch Syrup', /Batch Syrup 50ml/i);

    const cash = cashPay(page);
    await expect(cash).toBeDisabled();
    await expect(page.getByPlaceholder('Batch number', { exact: true })).toBeVisible();

    await page.getByPlaceholder('Batch number', { exact: true }).fill('LOT-POS');
    await expect(cash).toBeEnabled();
  });

  test('CG-30: serial-tracked POS item requires serials before it can be paid', async ({ page }) => {
    await loginAsOwner(page);
    await openPos(page);
    const box = page.getByPlaceholder(/scan barcode/i);
    await box.click();
    await box.fill('Ampoule');
    await page.getByRole('option', { name: /Serial Ampoule/i }).click();
    await expect(page.getByText(/serial number/i).first()).toBeVisible();
    await expect(cashPay(page)).toBeDisabled();
    await expect(box).toHaveValue(/Ampoule/i);

    await page.getByRole('button', { name: /^serials$/i }).click();
    await page.getByLabel(/^serials$/i).fill('SN-POS-1');
    await box.fill('');
    await box.fill('Ampoule');
    await page.getByRole('option', { name: /Serial Ampoule/i }).click();
    await expect(box).toHaveValue('');
    await expect(cashPay(page)).toBeEnabled();
  });

  test('CG-31: stock BLOCK disables pay when qty exceeds on-hand', async ({ page }) => {
    await loginAsOwnerStockBlock(page);
    await openPos(page);
    await addPosItem(page, 'Tea', /Premium Tea 500g/i);
    await fillLineQty(page, '41');
    await expect(cashPay(page)).toBeDisabled();
    await expect(page.getByText(/Insufficient stock/i).first()).toBeVisible();
  });

  test('cart table has an accessible name', async ({ page }) => {
    await loginAsOwner(page);
    await openPos(page);
    await expect(page.getByRole('table', { name: /cart|कार्ट/i })).toBeVisible();
  });
});
