import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';
import { loginAsOwner } from './helpers/auth';

test.describe('Help v0 (flag off)', () => {
  test('/help shows the v0 FAQ accordion', async ({ page }) => {
    await loginAsOwner(page);
    await page.goto('/help');
    await expect(page.getByRole('heading', { name: /help/i })).toBeVisible({ timeout: 15_000 });
    await expect(
      page.getByText(/How do I set the conversion rate between a base unit and an alternate unit/i),
    ).toBeVisible();
    await expect(page.getByLabel(/what are you trying to do/i)).toHaveCount(0);
  });

  test('/help has no serious/critical axe violations in the Help surface', async ({ page }) => {
    await loginAsOwner(page);
    await page.goto('/help');
    await expect(page.getByRole('heading', { name: /help/i })).toBeVisible({ timeout: 15_000 });
    const results = await new AxeBuilder({ page })
      .include('main')
      .withTags(['wcag2a', 'wcag2aa'])
      .analyze();
    const blocking = results.violations.filter((v) => v.impact === 'critical' || v.impact === 'serious');
    expect(blocking, JSON.stringify(blocking, null, 2)).toEqual([]);
  });
});

test.describe('Help v2 (e2e session hook, product flag still off)', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      sessionStorage.setItem('bizboard:e2eHelpV2', '1');
    });
  });

  test('/help shows the v2 search shell', async ({ page }) => {
    await loginAsOwner(page);
    await page.goto('/help');
    await expect(page.getByLabel(/what are you trying to do/i)).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText(/ask in your own words/i)).toBeVisible();
  });

  test('/help v2 has no serious/critical axe violations in the Help surface', async ({ page }) => {
    await loginAsOwner(page);
    await page.goto('/help');
    await expect(page.getByLabel(/what are you trying to do/i)).toBeVisible({ timeout: 15_000 });
    const results = await new AxeBuilder({ page })
      .include('main')
      .withTags(['wcag2a', 'wcag2aa'])
      .analyze();
    const blocking = results.violations.filter((v) => v.impact === 'critical' || v.impact === 'serious');
    expect(blocking, JSON.stringify(blocking, null, 2)).toEqual([]);
  });

  test('universal search offers a Help hit and opens the intent', async ({ page }, testInfo) => {
    // The AppBar hides UniversalSearch below the `sm` breakpoint (AppShell.tsx
    // renders it inside a `display: { xs: 'none', sm: 'flex' }` Box), so there
    // is no search box to find on the mobile project's viewport.
    testInfo.skip(testInfo.project.name === 'mobile', 'universal search is hidden below the sm breakpoint');
    await loginAsOwner(page);
    await page.goto('/');
    const search = page.getByRole('combobox', { name: /search invoices/i });
    await expect(search).toBeVisible({ timeout: 15_000 });
    await search.fill('how do i add gstin');
    await expect(page.getByRole('option', { name: /how do i add or change my gstin/i })).toBeVisible({
      timeout: 10_000,
    });
    await page.getByRole('option', { name: /how do i add or change my gstin/i }).click();
    await expect(page).toHaveURL(/intent=add-gstin/);
    await expect(page.getByText(/15-character GST number/i)).toBeVisible();
  });

  test('help health shows TTR and repeat metrics', async ({ page }) => {
    await loginAsOwner(page);
    await page.goto('/settings/help');
    await expect(page.getByRole('heading', { name: /help health/i })).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText(/time to resolution/i)).toBeVisible();
    await expect(page.getByText(/repeat/i).first()).toBeVisible();
  });

  test('Cancel this bill focuses the invoice cancel control', async ({ page }) => {
    await loginAsOwner(page);
    await page.goto('/help?intent=edit-completed-invoice&invoiceId=1');
    await expect(page.getByRole('link', { name: /cancel this bill/i })).toBeVisible({ timeout: 15_000 });
    await page.getByRole('link', { name: /cancel this bill/i }).click();
    await expect(page).toHaveURL(/helpAction=cancel/);
    await expect(page.locator('#invoice-cancel')).toBeVisible({ timeout: 15_000 });
  });
});

test.describe('Page contextual help', () => {
  test('invoice ? opens the drawer, closes, and Complete still works', async ({ page }, testInfo) => {
    await loginAsOwner(page);
    await page.goto('/sales/new', { waitUntil: 'domcontentloaded' });
    await expect(page.getByTestId('context-help-trigger')).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole('button', { name: /save & complete/i })).toBeVisible();

    const trigger = page.getByTestId('context-help-trigger');
    await expect(trigger).toBeVisible();
    await trigger.click();
    const drawer = page.getByTestId('context-help-drawer');
    await expect(drawer).toBeVisible();
    await expect(drawer.getByRole('heading', { name: /sales invoice/i })).toBeVisible();
    await expect(page).toHaveURL(/\/sales\/new/);

    const axe = await new AxeBuilder({ page })
      .include('[data-testid="context-help-drawer"]')
      .withTags(['wcag2a', 'wcag2aa'])
      .analyze();
    const blocking = axe.violations.filter((v) => v.impact === 'critical' || v.impact === 'serious');
    expect(blocking, JSON.stringify(blocking, null, 2)).toEqual([]);

    if (testInfo.project.name === 'mobile') {
      const box = await drawer.boundingBox();
      const vp = page.viewportSize();
      expect(box?.width ?? 0).toBeGreaterThan((vp?.width ?? 0) * 0.9);
    }

    await page.keyboard.press('Escape');
    await expect(drawer).toBeHidden();
    await expect(trigger).toHaveAttribute('aria-expanded', 'false');
    await expect(page).toHaveURL(/\/sales\/new/);

    await expect(page.locator('[data-help-slot="godown"]')).toBeVisible();
    await expect(page.locator('[data-help-slot="place-of-supply"]')).toBeVisible();
    await expect(page.locator('[data-help-slot="complete"]')).toBeVisible();

    await page.getByRole('combobox', { name: /bill to/i }).fill('Rahul');
    await page.getByRole('option', { name: /Rahul Stores/i }).click();
    const productBox = page.getByPlaceholder(/add item|search sku|search product/i);
    await productBox.click();
    await productBox.fill('Tea');
    await page.getByRole('option', { name: /Premium Tea 500g/i }).click();
    await expect(productBox).toHaveValue('');

    const complete = page.getByRole('button', { name: /save & complete/i });
    await expect(complete).toBeEnabled();
    await complete.click();
    await expect(page.getByTestId('context-help-drawer')).toHaveCount(0);
    await expect(page).not.toHaveURL(/\/help/);
    await expect(page).toHaveURL(/\/sales\/(new|history)/);
    await expect(page.getByRole('heading', { name: /invoice/i }).first()).toBeVisible();
  });
});
