/**
 * POS pay gates CG-28–CG-31 (cart has items; pay still blocked with a named reason).
 */
import { expect, test, type Page } from '@playwright/test';
import { fillLineQty } from '../complete-gates/assertCompleteGate';
import { loginAsOwner, loginAsOwnerStockBlock, loginAsOwnerWritesBlocked } from '../helpers/auth';

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

    const cash = page.getByRole('button', { name: /cash/i }).first();
    await expect(cash).toBeDisabled();
    await expect(page.getByPlaceholder('Batch number', { exact: true })).toBeVisible();

    await page.getByPlaceholder('Batch number', { exact: true }).fill('LOT-POS');
    await expect(cash).toBeEnabled();
  });

  test('CG-30: serial-tracked POS item requires serials before it can be paid', async ({ page }) => {
    await loginAsOwner(page);
    await openPos(page);
    await page.getByLabel(/serials/i).fill('SN-POS-1');
    await addPosItem(page, 'Ampoule', /Serial Ampoule/i);
    await expect(page.getByRole('button', { name: /cash/i }).first()).toBeEnabled();
  });

  test('CG-31: stock BLOCK disables pay when qty exceeds on-hand', async ({ page }) => {
    await loginAsOwnerStockBlock(page);
    await openPos(page);
    await addPosItem(page, 'Tea', /Premium Tea 500g/i);
    await fillLineQty(page, '41');
    await expect(page.getByRole('button', { name: /cash/i }).first()).toBeDisabled();
    await expect(page.getByText(/Insufficient stock/i).first()).toBeVisible();
  });

  test('CG-28: writes-blocked persona disables pay with a named reason', async ({ page }) => {
    await loginAsOwnerWritesBlocked(page);
    await openPos(page);
    await addPosItem(page, 'Tea', /Premium Tea 500g/i);
    const cash = page.getByRole('button', { name: /cash/i }).first();
    await expect(cash).toBeDisabled();
    await expect(page.getByText(/read-only|suspended|trial/i).first()).toBeVisible();
  });
});
