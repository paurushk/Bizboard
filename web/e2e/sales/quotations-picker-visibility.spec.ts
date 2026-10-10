import { expect, test } from '@playwright/test';
import { loginAsOwner } from '../helpers/auth';

/**
 * Regression guard for the QOS product-picker bug: this Autocomplete stages
 * the pick behind a separate Add button (QuotationEditorPage), so after clicking
 * an option the box must display the picked product — a stale query here
 * looks exactly like the click did nothing. No e2e coverage of this picker
 * existed before this pass.
 */
test.describe('quotations: product picker visibility', () => {
  test('new quotation: product picker shows the picked product, not the raw query', async ({ page }) => {
    await loginAsOwner(page);
    await page.goto('/sales/quotations/new', { waitUntil: 'domcontentloaded' });
    await expect(page.getByRole('heading', { name: /new quotation/i })).toBeVisible({
      timeout: 15_000,
    });

    const combo = page.getByRole('combobox', { name: 'Products', exact: true });
    await combo.click();
    await combo.fill('Premium');
    await page.getByRole('option', { name: /Premium Tea 500g/i }).click();
    await expect(combo).toHaveValue(/Premium Tea 500g/i);
  });
});
