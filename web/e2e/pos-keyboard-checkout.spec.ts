import { expect, test } from '@playwright/test';
import { loginAsSales } from './helpers/auth';

/**
 * G-6b (docs/TESTING_STRATEGY.md §7) — a complete POS sale, driven entirely
 * by keyboard, with focus staying in the scan field across the scan loop and
 * the whole checkout finishing under the H-02 budget (35s, no mouse).
 *
 * Extends the structural pattern already proven in pos-friction.spec.ts
 * (scan-field focus, no blocking dialog, focus survives typing) into a full
 * add -> adjust qty -> checkout flow. Zero `.click()` / `page.mouse` calls
 * anywhere in this file — every interaction is `.type()`, `.press()`, or
 * Locator.press() (which focuses the target itself, no pointer event).
 *
 * Uses the three mock products actually seeded (web/src/mocks/data.ts) as
 * three distinct cart lines — a literal "5 lines" would need fixture data
 * that doesn't exist yet; three real, distinct SKUs is a faithful stand-in
 * for the same claim (a multi-line sale is keyboard-completable).
 *
 * NOTE: written and reasoned through against the actual PosPage.tsx
 * implementation (exact-SKU-match-on-Enter in the scan Autocomplete,
 * self-clearing query field, tenderedAmount defaulting to the exact total
 * so Cash needs no typed amount) but not executed in this session — Bash
 * and the dev-server preview harness run in separate network sandboxes
 * here, so Playwright can't reach a server either way it's started. Run
 * `npm run test:e2e -- e2e/pos-keyboard-checkout.spec.ts` to confirm before
 * relying on it in CI.
 */
test('completes a keyboard-only sale across 3 lines, focus stays in the scan field, under the H-02 budget (G-6b)', async ({
  page,
}) => {
  await loginAsSales(page);
  await page.goto('/pos');
  await page.waitForLoadState('networkidle');

  const scan = page.getByPlaceholder(/scan barcode/i);
  await expect(scan).toBeFocused();
  await expect(page.getByRole('dialog')).toHaveCount(0);

  const start = Date.now();

  // Scan loop: type an exact SKU, Enter adds it (F2-052 exact-match-only),
  // the field self-clears (PosPage addProduct -> setProductQuery('')), so
  // the next scan just types straight in — focus never has to be reclaimed.
  for (const sku of ['TEA-500', 'OIL-1L', 'BTL-01']) {
    await page.keyboard.type(sku);
    await page.keyboard.press('Enter');
    await expect(scan).toBeFocused();
    await expect(page.getByText(sku, { exact: false }).first()).toBeVisible();
  }

  await expect(page.getByRole('dialog')).toHaveCount(0);

  // Bump the first line's quantity via the now-labeled stepper (G-6b a11y
  // fix) — Locator.press() focuses the target itself before sending the
  // key, so this stays pointer-free without a fragile manual Tab chain.
  const increaseFirstLine = page.getByLabel(/increase quantity/i).first();
  await increaseFirstLine.press('Enter');
  await expect(page.getByText('2', { exact: true }).first()).toBeVisible();

  // Tender and complete with Cash — tenderedAmount defaults to the exact
  // total when untouched (PosPage.tsx), so no amount needs to be typed.
  const cashButton = page.getByRole('button', { name: /cash/i }).first();
  await cashButton.press('Enter');

  await expect(page.getByText(/sale complete/i)).toBeVisible({ timeout: 15_000 });

  const elapsedMs = Date.now() - start;
  expect(elapsedMs, `POS checkout took ${elapsedMs}ms, H-02 budget is 35000ms`).toBeLessThan(35_000);
});
