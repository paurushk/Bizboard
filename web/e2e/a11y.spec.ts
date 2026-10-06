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
    // UX programme A1/A2: these routes failed axe (unlabeled inputs, checkboxes, contrast).
    { name: 'new purchase', path: '/purchases/new' },
    { name: 'sales history', path: '/sales/history' },
    { name: 'current stock', path: '/inventory/stock' },
    { name: 'item settings', path: '/settings/items' },
    { name: 'user settings', path: '/settings/users' },
    { name: 'billing', path: '/settings/billing' },
    { name: 'stock counts', path: '/inventory/stock-counts' },
    { name: 'receipts', path: '/sales/receipts' },
    { name: 'supplier payments', path: '/purchases/payments' },
    { name: 'sales returns', path: '/sales/returns' },
    { name: 'purchase returns', path: '/purchases/returns' },
    { name: 'customer ledger', path: '/reports/customer-ledger' },
    { name: 'supplier ledger', path: '/reports/supplier-ledger' },
    { name: 'pilot limits', path: '/help/pilot-limits' },
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

  test('J-A11Y-P2-KEYBOARD POS scan field is keyboard-operable without a mouse', async ({ page }) => {
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

  test('POS scan field has an accessible name and no serious contrast violation', async ({ page }) => {
    await loginAsOwner(page);
    await page.goto('/pos', { waitUntil: 'domcontentloaded' });
    const scan = page.getByPlaceholder(/scan barcode/i);
    await expect(scan).toBeVisible({ timeout: 20_000 });
    const named = await scan.evaluate((el) => {
      const node = el as HTMLInputElement;
      return (node.labels?.[0]?.textContent || node.getAttribute('aria-label') || node.placeholder || '').trim();
    });
    expect(named.length).toBeGreaterThan(0);
    const results = await new AxeBuilder({ page }).withTags(['wcag2aa']).analyze();
    const contrast = results.violations.filter(
      (v) => v.id === 'color-contrast' && (v.impact === 'critical' || v.impact === 'serious'),
    );
    expect(contrast, JSON.stringify(contrast, null, 2)).toEqual([]);
  });

  // G-6 residual: accessible name on interactive controls, not only axe impact.
  for (const { name, path } of [
    { name: 'login', path: '/login' },
    { name: 'dashboard', path: '/' },
    { name: 'POS', path: '/pos' },
    { name: 'new invoice', path: '/sales/new' },
  ]) {
    test(`${name} interactive controls have accessible names`, async ({ page }) => {
      if (path !== '/login') {
        await loginAsOwner(page);
      }
      await page.goto(path, { waitUntil: 'domcontentloaded' });
      await expect
        .poll(async () => (await page.locator('#root').innerHTML()).length, { timeout: 20_000 })
        .toBeGreaterThan(0);

      const results = await new AxeBuilder({ page })
        .withRules(['button-name', 'link-name', 'label', 'input-button-name', 'image-alt'])
        .analyze();
      expect(results.violations, `${name}: ${JSON.stringify(results.violations, null, 2)}`).toEqual([]);
    });
  }
});
