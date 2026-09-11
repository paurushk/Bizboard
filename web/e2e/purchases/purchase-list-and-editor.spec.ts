import { expect, test } from '@playwright/test';
import { loginAsOwner } from '../helpers/auth';

/**
 * Purchases domain, batch 1 — the Purchases equivalent of smoke.spec.ts's
 * completed-invoice freeze test and item-custom-fields.spec.ts's product-
 * picker flow (Purchases and Sales share the same NewPurchasePage /
 * NewInvoicePage editor shell and PartySelectPanel component).
 */
test.describe('purchases: history + editor', () => {
  test('purchase history list renders', async ({ page }) => {
    await loginAsOwner(page);
    await page.goto('/purchases/history', { waitUntil: 'domcontentloaded' });
    await expect(page.getByText(/PUR-2026-0001/i)).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText(/Western Distributors/i).first()).toBeVisible();
  });

  test('purchase detail page renders for a completed bill', async ({ page }) => {
    await loginAsOwner(page);
    await page.goto('/purchases/history/1', { waitUntil: 'domcontentloaded' });
    await expect(page.getByText(/PUR-2026-0001/i).first()).toBeVisible({ timeout: 15_000 });
  });

  test('completed purchase edit freezes the supplier Change control', async ({ page }) => {
    await loginAsOwner(page);
    await page.goto('/purchases/history/1/edit', { waitUntil: 'domcontentloaded' });
    await expect(page.getByText(/Western Distributors/i).first()).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole('button', { name: /^Change$/i })).toHaveCount(0);
  });

  test('new purchase: product picker filters and adds a line, picks a supplier, saves draft', async ({ page }) => {
    await loginAsOwner(page);
    await page.goto('/purchases/new', { waitUntil: 'domcontentloaded' });
    await expect(
      page.getByText(/new purchase/i).or(page.getByText(/bill from|supplier/i)).first(),
    ).toBeVisible({ timeout: 15_000 });

    const productBox = page.getByPlaceholder(/add item|search sku|search product/i);
    await productBox.click();
    await productBox.fill('Steel');
    await page.getByRole('option', { name: /Steel Bottle/i }).click();
    await expect(page.getByText('Steel Bottle').first()).toBeVisible();

    await page.getByRole('combobox', { name: /bill from/i }).fill('Western');
    await page.getByRole('option', { name: /Western Distributors/i }).click();
    await page.getByRole('button', { name: /save draft/i }).click();
    await expect(page.getByText(/draft .*saved|saved/i).first()).toBeVisible({ timeout: 15_000 });
  });
});
