import { expect, test } from '@playwright/test';
import { loginAsSales } from './helpers/auth';

/**
 * G-6b (docs/TESTING_STRATEGY.md §7) — a keyboard-only POS add/adjust flow,
 * with focus staying in the scan field across the scan loop, under the H-02
 * budget (35s, no mouse) for reaching a pay-ready cart.
 *
 * Deliberately stops short of completing the sale. web/e2e-golden/
 * pos-golden-path.spec.ts's own docstring already documents why: "no
 * existing golden spec (nor the mocked web/e2e/ pos-friction.spec.ts, which
 * never completes a real sale)" proves a POS checkout end-to-end — because
 * `previewSalesTotals()` (src/api/legacy/sales.ts) is not wrapped in
 * withMocks() and always calls the real backend. Confirmed live in this
 * session (2026-09-13, manual verification below): clicking Cash in the
 * pure-mocked `e2e` project surfaces "Could not confirm till total from
 * server. Retry pay." every time, with no backend to answer it. A full
 * paid-checkout keyboard journey belongs in e2e-golden (real backend),
 * matching pos-golden-path.spec.ts's own lane — not duplicated here with an
 * approximated mock for a widely-shared totals-preview function used by
 * NewInvoicePage/NewPurchasePage too, which risks silently drifting from
 * real backend tax/rounding behavior.
 *
 * Extends the structural pattern already proven in pos-friction.spec.ts
 * (scan-field focus, no blocking dialog, focus survives typing) as far as
 * this lane can honestly go: add -> adjust qty -> pay-ready. Zero
 * `.click()` / `page.mouse` calls — every interaction is `.type()`,
 * `.press()`, or Locator.press() (focuses the target itself, no pointer event).
 *
 * Uses the mock products seeded in web/src/mocks/data.ts as
 * three distinct cart lines — a literal "5 lines" would need fixture data
 * that doesn't exist yet; three real, distinct SKUs is a faithful stand-in
 * for the same claim (a multi-line sale is keyboard-completable).
 *
 * VERIFIED 2026-09-13 via manual browser-pane walkthrough against a live
 * `vite --mode e2e` dev server (this sandboxed session can't run Playwright
 * itself — Bash and the dev-server preview harness are in separate network
 * sandboxes — so this was driven by hand through the same app code with
 * genuine DOM KeyboardEvents to prove the underlying behavior, not narrated
 * from reading the source): scan-field autofocus, exact-SKU Enter-to-add,
 * self-clearing query field, the qty +/- aria-label fix, and the Cash
 * button all behave exactly as this spec asserts. One tool-specific caveat
 * found along the way and NOT a product bug: the manual browser-automation
 * tool's synthetic "Return" keypress didn't register on this MUI
 * Autocomplete (a real `new KeyboardEvent('keydown', {key:'Enter'})`
 * dispatch did, immediately) — Playwright's `keyboard.press()` sends
 * trusted-equivalent, real OS-level events and does not share this
 * limitation, but run this once for real before trusting it in CI anyway,
 * per standing practice for anything not executed by an actual Playwright run.
 */
test('adds 3 lines and adjusts quantity keyboard-only, focus stays in the scan field, cart is pay-ready under the H-02 budget (G-6b)', async ({
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
  // Qty lives in NumericField (an input value, not a text node).
  const firstLine = page.locator('tr').filter({ hasText: 'TEA-500' });
  await firstLine.getByLabel(/increase quantity/i).press('Enter');
  await expect(firstLine.getByRole('textbox').first()).toHaveValue('2');

  // Cart is pay-ready: a real total is showing and the Cash button carries
  // it (PosPage renders `Cash — ${amount}` once cart.length > 0), all
  // reached without a single mouse interaction.
  const cashButton = page.getByRole('button', { name: /cash — ₹\d/i });
  await expect(cashButton).toBeVisible();
  await expect(cashButton).toBeEnabled();

  const elapsedMs = Date.now() - start;
  expect(elapsedMs, `keyboard add+adjust took ${elapsedMs}ms, H-02 budget is 35000ms`).toBeLessThan(
    35_000,
  );
});
