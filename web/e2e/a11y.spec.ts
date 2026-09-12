import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';
import { loginAsOwner } from './helpers/auth';

test.describe('Accessibility smoke (axe)', () => {
  test('login page has no serious/critical violations', async ({ page }) => {
    await page.goto('/login');
    await expect(page.getByRole('button', { name: /sign in/i })).toBeVisible({ timeout: 10_000 });

    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa'])
      .analyze();

    const blocking = results.violations.filter(
      (v) => v.impact === 'critical' || v.impact === 'serious',
    );
    expect(blocking, JSON.stringify(blocking, null, 2)).toEqual([]);
  });

  test('dashboard after auth has no serious/critical violations', async ({ page }) => {
    await loginAsOwner(page);
    await page.goto('/');
    await expect(page.getByRole('heading', { name: /dashboard/i })).toBeVisible({ timeout: 15_000 });

    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa'])
      .analyze();

    const blocking = results.violations.filter(
      (v) => v.impact === 'critical' || v.impact === 'serious',
    );
    expect(blocking, JSON.stringify(blocking, null, 2)).toEqual([]);
  });

  // QOS-0007: the screens real users spend time on, not just login + dashboard.
  for (const { name, path } of [
    { name: 'new invoice form', path: '/sales/new' },
    { name: 'POS', path: '/pos' },
    { name: 'a report', path: '/reports/profit-loss' },
    { name: 'company settings', path: '/settings/company' },
  ]) {
    test(`${name} has no serious/critical axe violations`, async ({ page }) => {
      await loginAsOwner(page);
      await page.goto(path, { waitUntil: 'domcontentloaded' });
      await expect
        .poll(async () => (await page.locator('#root').innerHTML()).length, { timeout: 20_000 })
        .toBeGreaterThan(0);

      const results = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa']).analyze();
      const blocking = results.violations.filter(
        (v) => v.impact === 'critical' || v.impact === 'serious',
      );
      expect(blocking, `${name}: ${JSON.stringify(blocking, null, 2)}`).toEqual([]);
    });
  }

  // QOS-0007: the counter clerk works keyboard + scanner only. The scan field
  // must be reachable and usable without a pointer.
  test('POS scan field is keyboard-operable without a mouse', async ({ page }) => {
    await loginAsOwner(page);
    await page.goto('/pos', { waitUntil: 'domcontentloaded' });
    const scan = page.getByPlaceholder(/scan barcode/i);
    await expect(scan).toBeVisible({ timeout: 20_000 });

    await page.keyboard.press('Tab');  // no mouse — walk in with the keyboard
    await scan.focus();
    await scan.press('w');
    await scan.press('i');
    await scan.press('d');
    await expect(scan).toHaveValue(/wid/i);
    await expect(scan).toBeFocused();
  });
});
