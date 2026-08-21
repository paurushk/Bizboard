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
});
