import { expect, test } from '@playwright/test';
import { loginAsOwner } from './helpers/auth';

test.describe('Item custom fields v1', () => {
  test('Items list shows custom columns, filters, and column picker prefs', async ({ page }) => {
    await loginAsOwner(page);
    await page.goto('/inventory/products');
    await expect(page.getByRole('heading', { name: /items|products/i }).first()).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByRole('columnheader', { name: 'Brand form' })).toBeVisible();
    await expect(page.getByText('Premium Tea 500g')).toBeVisible();

    await page.getByRole('combobox', { name: /brand form/i }).click();
    await page.getByRole('option', { name: 'Strip' }).click();
    await expect(page.getByText('Premium Tea 500g')).toBeVisible();
    await expect(page.getByText('Cooking Oil 1L')).toHaveCount(0);

    await page.getByRole('button', { name: /^columns$/i }).click();
    await page.getByRole('checkbox', { name: 'Brand form' }).uncheck();
    await page.keyboard.press('Escape');
    await expect(page.getByRole('columnheader', { name: 'Brand form' })).toHaveCount(0);

    await page.reload();
    await expect(page.getByRole('heading', { name: /items|products/i }).first()).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByRole('columnheader', { name: 'Brand form' })).toHaveCount(0);
  });

  test('Current stock filters by list custom field', async ({ page }) => {
    await loginAsOwner(page);
    await page.goto('/inventory/stock');
    await expect(page.getByRole('heading', { name: /current stock/i })).toBeVisible({ timeout: 15_000 });
    await page.getByRole('combobox', { name: /brand form/i }).click();
    await page.getByRole('option', { name: 'Strip' }).click();
    await expect(page.getByText('Premium Tea 500g')).toBeVisible();
    await expect(page.getByText('Cooking Oil 1L')).toHaveCount(0);

    await page.goto('/inventory/stock');
    await page.getByPlaceholder(/search name, sku, barcode, or custom value/i).fill('Red');
    await expect(page.getByText('Premium Tea 500g')).toBeVisible();
    await expect(page.getByText('Cooking Oil 1L')).toHaveCount(0);
  });

  test('sales product picker can filter by Brand form and add the item', async ({ page }) => {
    await loginAsOwner(page);
    await page.goto('/sales/new');
    await expect(page.getByRole('heading', { name: /new invoice|sales invoice/i }).or(page.getByText(/bill to|customer/i)).first()).toBeVisible({
      timeout: 15_000,
    });
    await page.getByRole('button', { name: /filters/i }).click();
    await page.getByRole('combobox', { name: /brand form/i }).click();
    await page.getByRole('option', { name: 'Strip' }).click();
    await page.keyboard.press('Escape');
    const productBox = page.getByPlaceholder(/add item|search sku|search product/i);
    await productBox.click();
    await productBox.fill('Premium');
    await page.getByRole('option', { name: /Premium Tea/i }).click();
    await expect(page.getByText('Premium Tea 500g').first()).toBeVisible();

    await page.getByRole('combobox', { name: /bill to/i }).fill('Ra');
    await page.getByRole('option', { name: /Rahul Stores/i }).click();
    await page.getByRole('button', { name: /save draft/i }).click();
    await expect(page.getByText(/draft .*saved|saved/i).first()).toBeVisible({ timeout: 15_000 });
  });

  test('POS finder filters by Brand form; barcode exact-match ignores the filter', async ({ page }) => {
    await loginAsOwner(page);
    await page.goto('/pos');
    await expect(page.getByRole('heading', { name: /point of sale/i })).toBeVisible({ timeout: 15_000 });
    await page.getByRole('button', { name: /filters/i }).click();
    await page.getByRole('combobox', { name: /brand form/i }).click();
    await page.getByRole('option', { name: 'Strip' }).click();
    await page.keyboard.press('Escape');
    const search = page.getByPlaceholder(/scan barcode or search product/i);
    await search.fill('8901234567891');
    await search.press('Enter');
    await expect(page.getByText('Cooking Oil 1L')).toBeVisible({ timeout: 10_000 });
  });

  test('Item Settings exposes type and list options', async ({ page }) => {
    await loginAsOwner(page);
    await page.goto('/settings/items');
    await expect(page.getByRole('heading', { name: /item settings/i })).toBeVisible({ timeout: 15_000 });
    await expect(page.getByLabel(/^type$/i).first()).toBeVisible();
    await expect(page.getByText('Strip')).toBeVisible();
  });

  test('Edit Item round-trips camelCase custom values', async ({ page }) => {
    await loginAsOwner(page);
    await page.goto('/inventory/products');
    await expect(page.getByText('Premium Tea 500g')).toBeVisible({ timeout: 15_000 });
    await page.getByRole('row', { name: /Premium Tea 500g/ }).getByRole('button', { name: /^edit$/i }).click();
    await page.getByRole('tab', { name: /custom fields/i }).click();
    await expect(page.getByLabel(/^color$/i)).toHaveValue('Red');
    await page.getByLabel(/^color$/i).fill('Crimson');
    await expect(page.getByRole('button', { name: /save item/i })).toBeEnabled();
    await page.getByRole('button', { name: /save item/i }).click();
    await expect(page.getByRole('dialog')).toHaveCount(0, { timeout: 15_000 });
    await page.getByRole('row', { name: /Premium Tea 500g/ }).getByRole('button', { name: /^edit$/i }).click();
    await page.getByRole('tab', { name: /custom fields/i }).click();
    await expect(page.getByLabel(/^color$/i)).toHaveValue('Crimson');
  });
});
