import { expect, test } from '@playwright/test';
import { loginAsOwner } from './helpers/auth';

/**
 * Quick Order Entry smoke (mock data): book an order in a few taps, type a quantity, Save & next, and keep the page
 * inside the viewport on a phone.
 */
test.describe('Quick order entry', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsOwner(page);
    await page.goto('/sales/quick-entry');
    await expect(page.getByRole('heading', { name: 'Quick order entry' })).toBeVisible();
  });

  async function pickCustomerAndProduct(page: import('@playwright/test').Page) {
    await page.getByLabel('Search a customer').click();
    await page.getByRole('option').first().click();
    await page.getByLabel('Search a product').click();
    await page.getByRole('option').first().click();
  }

  test('books a draft bill with a typed quantity and starts the next order', async ({ page }) => {
    await pickCustomerAndProduct(page);
    const qty = page.getByLabel(/^Quantity for /);
    await expect(qty).toHaveValue('1');
    await qty.fill('12');
    await qty.blur();
    await expect(qty).toHaveValue('12');
    // The decrease button never deletes the line.
    await page.getByLabel(/^Decrease quantity /).click();
    await expect(qty).toHaveValue('11');

    await page.getByRole('button', { name: /Save draft bill & next/ }).click();
    await expect(page.getByText(/Draft bill .* saved\./)).toBeVisible();
    await expect(page.getByLabel(/^Quantity for /)).toHaveCount(0);
    await expect(page.getByLabel('Search a customer')).toBeVisible();
  });

  test('a removed line can be restored with Undo', async ({ page }) => {
    await pickCustomerAndProduct(page);
    await page.getByLabel(/^Remove /).click();
    await expect(page.getByLabel(/^Quantity for /)).toHaveCount(0);
    await page.getByRole('button', { name: 'Undo' }).click();
    await expect(page.getByLabel(/^Quantity for /)).toHaveCount(1);
  });

  test('does not scroll sideways on a phone and keeps the controls tappable', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await pickCustomerAndProduct(page);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(0);
    const box = await page.getByLabel(/^Increase quantity /).boundingBox();
    expect(box?.width ?? 0).toBeGreaterThanOrEqual(44);
    expect(box?.height ?? 0).toBeGreaterThanOrEqual(44);
  });
});
