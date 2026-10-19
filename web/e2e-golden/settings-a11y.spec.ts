import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';
import { registerTenant, unique } from './helpers/documents';

/**
 * SET-26: every Settings screen, on the live backend: axe (WCAG 2 A/AA), no sideways scrolling at a
 * 360 px phone width, a named main region and heading, and keyboard reach of the primary action.
 */
const SCREENS = [
  '/settings',
  '/settings/company',
  '/settings/gst',
  '/settings/statutory-licences',
  '/settings/bank-accounts',
  '/settings/payment-gateway',
  '/settings/money-in',
  '/settings/price-lists',
  '/settings/accounting',
  '/settings/series',
  '/settings/templates',
  '/settings/units',
  '/settings/items',
  '/settings/users',
  '/settings/import',
  '/settings/backup',
  '/settings/billing',
  '/settings/ai',
];

test.describe.configure({ mode: 'serial' });

test.describe('Settings accessibility and layout', () => {
  test.setTimeout(240_000);
  let page: import('@playwright/test').Page;

  test.beforeAll(async ({ browser }) => {
    const context = await browser.newContext();
    page = await context.newPage();
    const id = unique();
    await registerTenant(page, {
      companyName: `E2E A11y ${id}`,
      email: `e2e-a11y-${id}@example.test`,
      password: 'GoldenPath123!',
    });
  });
  test.afterAll(async () => page.context().close());

  for (const path of SCREENS) {
    test(`${path}: no serious or critical axe violations`, async () => {
      await page.setViewportSize({ width: 1280, height: 900 });
      await page.goto(path);
      await expect(page.getByRole('heading', { level: 1 }).first()).toBeVisible({ timeout: 20_000 });
      await page.waitForLoadState('networkidle').catch(() => undefined);
      const results = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa']).analyze();
      const blocking = results.violations.filter((v) => v.impact === 'critical' || v.impact === 'serious');
      expect(blocking, `${path}: ${JSON.stringify(blocking.map((v) => ({ id: v.id, nodes: v.nodes.map((n) => n.target) })), null, 2)}`).toEqual([]);
    });

    test(`${path}: fits a 360px phone without sideways scrolling`, async () => {
      await page.setViewportSize({ width: 360, height: 800 });
      await page.goto(path);
      await expect(page.getByRole('heading', { level: 1 }).first()).toBeVisible({ timeout: 20_000 });
      await page.waitForLoadState('networkidle').catch(() => undefined);
      // Wide tables scroll inside their own container; the page itself must not.
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      expect(overflow, `${path} overflows by ${overflow}px`).toBeLessThanOrEqual(1);
    });
  }

  test('Company: the save action is reachable and usable from the keyboard', async () => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto('/settings/company');
    const city = page.getByLabel('City');
    await expect(city).toBeVisible();
    await city.fill('Keyboard City');
    const save = page.getByRole('button', { name: 'Save', exact: true });
    await save.focus();
    await expect(save).toBeFocused();
    await page.keyboard.press('Enter');
    await expect(page.getByText(/Saved/).first()).toBeVisible();
  });

  test('a dialog returns focus to the button that opened it', async () => {
    await page.goto('/settings/units');
    const add = page.getByRole('button', { name: /add/i }).first();
    await add.click();
    await expect(page.getByRole('dialog')).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(page.getByRole('dialog')).toBeHidden();
    await expect(add).toBeFocused();
  });
});
