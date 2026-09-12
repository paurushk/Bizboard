import { expect, test } from '@playwright/test';
import { loginAsSales } from './helpers/auth';

/**
 * QOS-0017 — POS counter friction budget. The archetype matrix names modal
 * popups and keyboard-focus loss as the ARCH-01 pain points; a change that
 * reintroduces a blocking modal into the scan loop, or steals focus off the
 * scan field on load, should fail here.
 */
test.describe('POS friction', () => {
  test('opens with the scan field focused and no blocking dialog', async ({ page }) => {
    await loginAsSales(page);
    await page.goto('/pos');
    await page.waitForLoadState('networkidle');

    // no modal dialog is up when the counter clerk arrives
    await expect(page.getByRole('dialog')).toHaveCount(0);

    // the scan / search field owns focus so the first scan just works
    const scan = page.getByPlaceholder(/scan barcode/i);
    await expect(scan).toBeVisible();
    await expect(scan).toBeFocused();
  });

  test('exactly one tender button is emphasised as the remembered default (QOS-0040)', async ({ page }) => {
    await loginAsSales(page);
    await page.goto('/pos');
    await page.waitForLoadState('networkidle');

    const cash = page.getByRole('button', { name: /cash|finish payment/i }).first();
    const upi = page.getByRole('button', { name: /upi/i }).first();
    await expect(cash).toBeVisible();
    await expect(upi).toBeVisible();

    const emphasised = async (b: typeof cash) =>
      (await b.evaluate((el) => el.className)).includes('MuiButton-contained');
    // one primary (the remembered method), one secondary — never both, never neither
    expect(Number(await emphasised(cash)) + Number(await emphasised(upi))).toBe(1);
  });

  test('typing a query keeps focus in the scan field (no focus theft)', async ({ page }) => {
    await loginAsSales(page);
    await page.goto('/pos');
    await page.waitForLoadState('networkidle');

    const scan = page.getByPlaceholder(/scan barcode/i);
    await scan.focus();
    await page.keyboard.type('wid');
    // a results dropdown may appear, but focus must remain in the input
    await expect(scan).toBeFocused();
    await expect(page.getByRole('dialog')).toHaveCount(0);
  });
});
