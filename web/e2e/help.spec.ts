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

  test('universal search offers a Help hit and opens the intent', async ({ page }) => {
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
