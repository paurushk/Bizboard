import { expect, test } from '@playwright/test';
import { loginAsOwner } from '../helpers/auth';

/**
 * Bill upload review (UPLOAD_SALES_BILL_REVIEW.md), run against the mock API so it needs no backend or AI:
 * job 1000 is a small sales bill with row positions, job 999 a 150-row bill.
 * Runs on both the desktop and the `mobile` (Pixel 5) projects.
 */
test.describe('bill upload review', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsOwner(page);
    await page.evaluate(() => window.localStorage.removeItem('billUpload.showSource'));
  });

  test('a phone-width screen does not scroll sideways and shows the bill in a drawer', async ({ page }, info) => {
    test.skip(info.project.name !== 'mobile', 'phone-width check');
    await page.goto('/sales/bill-upload?job=1000');
    await expect(page.getByText('Mock item 1').first()).toBeVisible({ timeout: 20_000 });
    const overflow = await page.evaluate(() => {
      const d = document.documentElement;
      return d.scrollWidth - d.clientWidth;
    });
    expect(overflow, 'page content wider than the screen').toBeLessThanOrEqual(2);
    // The table scrolls inside its own container instead of widening the page.
    const tableScrollsInside = await page.evaluate(() => {
      const table = document.querySelector('table');
      const box = table?.parentElement;
      return !!box && getComputedStyle(box).overflowX === 'auto';
    });
    expect(tableScrollsInside).toBe(true);
    await page.getByRole('button', { name: 'Show the original bill' }).click();
    const drawer = page.locator('.MuiDrawer-anchorBottom');
    await expect(drawer.getByRole('img', { name: 'Original bill' })).toBeVisible();
  });

  test('the original bill sits beside the rows and the row you point at is outlined', async ({ page }, info) => {
    test.skip(info.project.name === 'mobile', 'side-by-side layout needs a wide screen');
    await page.setViewportSize({ width: 1500, height: 900 });
    await page.goto('/sales/bill-upload?job=1000');
    const image = page.getByRole('img', { name: 'Original bill' });
    await expect(image).toBeVisible({ timeout: 20_000 });
    await expect(page.getByTestId('bill-row-highlight')).toHaveCount(0);
    await page.getByRole('button', { name: 'Expand row to edit details' }).first().hover();
    const box = page.getByTestId('bill-row-highlight');
    await expect(box).toBeVisible();
    // The outline lands on the row's position (8% across, 30% down) of the picture.
    const [imgBox, outline] = [await image.boundingBox(), await box.boundingBox()];
    expect(Math.abs(outline!.x - (imgBox!.x + imgBox!.width * 0.08))).toBeLessThan(3);
    expect(Math.abs(outline!.y - (imgBox!.y + imgBox!.height * 0.3))).toBeLessThan(3);
  });

  test('a 150-row bill keeps only the rows on screen in the page and still scrolls', async ({ page }, info) => {
    test.skip(info.project.name === 'mobile', 'windowing check runs on desktop');
    await page.setViewportSize({ width: 1500, height: 900 });
    await page.goto('/sales/bill-upload?job=999');
    await expect(page.getByText('Mock item 1').first()).toBeVisible({ timeout: 20_000 });
    const drawn = await page.locator('tr[data-index]').count();
    expect(drawn).toBeGreaterThan(5);
    expect(drawn).toBeLessThan(60);
    const firstAfter = await page.evaluate(async () => {
      const region = [...document.querySelectorAll('[role=region]')].find((e) => e.querySelector('table')) as HTMLElement;
      region.scrollTop = 6000;
      region.dispatchEvent(new Event('scroll'));
      await new Promise((r) => setTimeout(r, 800));
      return Number((document.querySelector('tr[data-index]') as HTMLElement).dataset.index);
    });
    expect(firstAfter).toBeGreaterThan(60);
  });

  test('Upload Sales Bill is in the Sales menu, not under More', async ({ page }, info) => {
    test.skip(info.project.name === 'mobile', 'menu is collapsed on a phone');
    await page.setViewportSize({ width: 1500, height: 900 });
    await page.goto('/sales/bill-upload');
    const nav = page.getByRole('navigation').first();
    await expect(nav.getByRole('link', { name: 'Upload Sales Bill' })).toBeVisible({ timeout: 20_000 });
  });
});
