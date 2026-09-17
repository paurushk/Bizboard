import { expect, test } from '@playwright/test';
import { registerTenant, unique } from './helpers/documents';

/**
 * QOS-0016 — observe Dashboard first KPI paint. Not a signed SLO.
 * Volume soak for ReportService.dashboard lives in
 * backend/tests/test_qos0016_dashboard_budget.py (400 COMPLETED invoices).
 * A 12-month Playwright p95 remains Human / founder-owned.
 */
test('dashboard first KPI paint is observed under a loose budget', async ({ page }) => {
  test.setTimeout(90_000);
  const id = unique();
  await registerTenant(page, {
    companyName: `E2E Dash ${id}`,
    email: `e2e-dash-${id}@example.test`,
    password: 'GoldenPath123!',
  });

  const start = Date.now();
  await page.goto('/');
  await expect(page.getByRole('heading', { name: /^Dashboard$/i })).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText('Customer outstanding')).toBeVisible({ timeout: 15_000 });
  const elapsed = Date.now() - start;
  expect(elapsed, `dashboard first paint ${elapsed}ms (observation budget 15s)`).toBeLessThan(15_000);
});
