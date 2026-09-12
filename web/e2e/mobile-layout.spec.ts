import { expect, test } from '@playwright/test';
import { loginAsOwner } from './helpers/auth';

/**
 * QOS-0026 (UX-003/004/005 regression): at a phone-width viewport, key screens
 * must not overflow the body horizontally and the page title must not be
 * occluded. Runs on the `mobile` (Pixel 5) project.
 */
test.describe('mobile layout — no horizontal overflow', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsOwner(page);
  });

  for (const { name, path } of [
    { name: 'dashboard', path: '/' },
    { name: 'attention queue', path: '/attention' },
    { name: 'POS', path: '/pos' },
  ]) {
    test(`${name} does not scroll horizontally`, async ({ page }) => {
      await page.goto(path);
      await page.waitForLoadState('networkidle');
      const overflow = await page.evaluate(() => {
        const d = document.documentElement;
        return { scrollW: d.scrollWidth, clientW: d.clientWidth };
      });
      // allow a 2px rounding slack
      expect(
        overflow.scrollW - overflow.clientW,
        `${overflow.scrollW}px content in a ${overflow.clientW}px viewport`,
      ).toBeLessThanOrEqual(2);
    });
  }
});
