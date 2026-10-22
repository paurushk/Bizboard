import { expect, test } from '@playwright/test';
import { seedTwelveMonthsOfInvoices } from './helpers/grantFlag';
import { registerTenant, unique } from './helpers/documents';

/**
 * QOS-0016 — Dashboard render p95 on a company with twelve months of trading.
 *
 * The company gets E2E_DASHBOARD_INVOICES completed invoices (default 180, one about every two days over the
 * last 360 days, with returns and part-paid receipts) through SalesService.complete, so the
 * dashboard reads real lines, stock, receipts and ledger rows. The page is then loaded
 * E2E_DASHBOARD_SAMPLES times after one warm-up load and the nearest-rank p95 of
 * "navigation start -> Customer outstanding KPI visible" must stay under E2E_DASHBOARD_P95_MS.
 *
 * Budget: docs/ops/SLO.md gives the dashboard API a 2 s p95. The browser number adds the SPA's
 * own requests and rendering on the CI dev server. Two runs on one laptop (Postgres in Docker, Vite dev
 * server) measured p95 2.8 s and 6.0 s, so the default budget is 8 s: it catches a regression of
 * several times, not drift. Tighten it once hosted staging numbers exist (docs/ops/LOAD_RESULTS_TEMPLATE.md).
 */
const INVOICES = Number(process.env.E2E_DASHBOARD_INVOICES || 180);
const SAMPLES = Number(process.env.E2E_DASHBOARD_SAMPLES || 10);
const P95_BUDGET_MS = Number(process.env.E2E_DASHBOARD_P95_MS || 8_000);

function nearestRankP95(values: number[]): number {
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.max(0, Math.ceil(0.95 * sorted.length) - 1)];
}

test('dashboard p95 stays within budget on twelve months of invoices', async ({ page }) => {
  test.setTimeout(25 * 60_000);
  const id = unique();
  const companyName = `E2E Dash12 ${id}`;
  const password = 'GoldenPath123!';
  await registerTenant(page, { companyName, email: `e2e-dash12-${id}@example.test`, password });

  await seedTwelveMonthsOfInvoices(companyName, password, INVOICES);

  const load = async () => {
    const start = Date.now();
    await page.goto('/');
    await expect(page.getByRole('heading', { name: /^Dashboard$/i })).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText('Customer outstanding')).toBeVisible({ timeout: 30_000 });
    return Date.now() - start;
  };

  await load(); // warm-up: dev-server module transform and the first query plans
  const samples: number[] = [];
  for (let i = 0; i < SAMPLES; i += 1) samples.push(await load());

  const p95 = nearestRankP95(samples);
  const median = [...samples].sort((a, b) => a - b)[Math.floor(samples.length / 2)];
  test.info().annotations.push({
    type: 'dashboard-render',
    description: `invoices=${INVOICES} samples=${samples.join(',')} p95=${p95}ms median=${median}ms budget=${P95_BUDGET_MS}ms`,
  });
  console.log(`QOS-0016 dashboard render: invoices=${INVOICES} samples=[${samples.join(', ')}] p95=${p95}ms`);
  expect(p95, `dashboard p95 ${p95}ms over ${SAMPLES} loads (budget ${P95_BUDGET_MS}ms)`).toBeLessThan(P95_BUDGET_MS);
});
