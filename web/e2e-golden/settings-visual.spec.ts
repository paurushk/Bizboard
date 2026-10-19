import { expect, test, type Page } from '@playwright/test';
import { registerTenant, unique } from './helpers/documents';

/**
 * SET-25: every Settings screen in English and Hindi, captured and compared with a stored image. (The
 * app has no dark theme, so there is no dark variant to compare.)
 * Only the main content area is compared; the page header and menu carry the tenant's name and email,
 * which change on every run. Dates and times inside the content are masked.
 *
 * Update the stored images after an intended change with:
 *   E2E_VISUAL=1 npx playwright test -c playwright.golden.config.ts e2e-golden/settings-visual.spec.ts --update-snapshots
 */
const SCREENS: Array<[string, string]> = [
  ['hub', '/settings'],
  ['company', '/settings/company'],
  ['gst', '/settings/gst'],
  ['licences', '/settings/statutory-licences'],
  ['banks', '/settings/bank-accounts'],
  ['gateway', '/settings/payment-gateway'],
  ['money-in', '/settings/money-in'],
  ['price-lists', '/settings/price-lists'],
  ['accounting', '/settings/accounting'],
  ['series', '/settings/series'],
  ['templates', '/settings/templates'],
  ['units', '/settings/units'],
  ['items', '/settings/items'],
  ['users', '/settings/users'],
  ['import', '/settings/import'],
  ['backup', '/settings/backup'],
  ['billing', '/settings/billing'],
  ['ai', '/settings/ai'],
];

// The stored images were taken with Chrome on Windows; other platforms render text slightly
// differently, so the comparison runs only when asked for (E2E_VISUAL=1) on a matching machine.
test.skip(process.env.E2E_VISUAL !== '1', 'visual comparison is opt-in: set E2E_VISUAL=1');

test.describe.configure({ mode: 'serial' });

test.describe('Settings visual consistency', () => {
  test.setTimeout(300_000);
  let page: Page;

  test.beforeAll(async ({ browser }) => {
    const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    page = await context.newPage();
    const id = unique();
    await registerTenant(page, {
      companyName: `Visual Traders`,
      email: `e2e-visual-${id}@example.test`,
      password: 'GoldenPath123!',
    });
  });
  test.afterAll(async () => page.context().close());

  async function settle(path: string) {
    await page.goto(path);
    await expect(page.getByRole('heading', { level: 1 }).first()).toBeVisible({ timeout: 20_000 });
    await page.waitForLoadState('networkidle').catch(() => undefined);
    await page.addStyleTag({ content: '*{animation:none!important;transition:none!important;caret-color:transparent!important}' });
  }

  const main = () => page.locator('#main-content');
  const masks = () => [page.getByRole('banner'), main().getByText(/\d{1,2}\/\d{1,2}\/\d{2,4}|\d{1,2}:\d{2}/), main().locator('[data-volatile]')];

  for (const [name, path] of SCREENS) {
    test(`${name}: English`, async () => {
      await settle(path);
      await expect(main()).toHaveScreenshot(`${name}-light.png`, { mask: masks(), maxDiffPixelRatio: 0.02 });
    });
  }

  test('switch to Hindi', async () => {
    await page.goto('/settings');
    await page.getByRole('button', { name: 'हिंदी' }).click();
  });
  for (const [name, path] of SCREENS) {
    test(`${name}: Hindi`, async () => {
      await settle(path);
      await expect(main()).toHaveScreenshot(`${name}-hi.png`, { mask: masks(), maxDiffPixelRatio: 0.02 });
    });
  }
});
