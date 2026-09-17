import { expect, test } from '@playwright/test';
import { loginAsOwner } from '../helpers/auth';

/**
 * Regression guard for the QOS product-picker bug: this Autocomplete stages
 * the pick (no auto-clear on select), so after clicking an option the box
 * must display the picked product — a stale query here looks exactly like
 * the click did nothing. No e2e coverage of this picker existed before this
 * pass.
 *
 * A StockTransferPage case was dropped here on purpose: its listWarehouses/
 * listTransfers calls bypass the app's withMocks() layer entirely (unlike
 * listStock, which has a proper mock fallback), so the page can't render in
 * this mock-only e2e environment at all — that's a pre-existing mocking gap,
 * unrelated to the picker bug this file guards against.
 */
test.describe('inventory: product picker visibility', () => {
  test('stock adjustment: product picker shows the picked product, not the raw query', async ({ page }) => {
    await loginAsOwner(page);
    await page.goto('/inventory/adjustments', { waitUntil: 'domcontentloaded' });
    await expect(page.getByRole('heading', { name: /stock adjustment/i })).toBeVisible({
      timeout: 15_000,
    });

    const combo = page.getByRole('combobox', { name: 'Products', exact: true });
    await combo.click();
    await combo.fill('Premium');
    await page.getByRole('option', { name: /Premium Tea 500g/i }).click();
    await expect(combo).toHaveValue(/Premium Tea 500g/i);
  });
});
