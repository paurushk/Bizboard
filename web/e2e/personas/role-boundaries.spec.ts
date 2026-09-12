/**
 * §H1 — frontend persona counterparts of backend/tests/personas/.
 *
 * The backend PJ-* journeys prove the API enforces each role's boundary; these
 * prove the UI HIDES what the role cannot do (no dead buttons that 403). One
 * describe block per persona, mirroring the backend matrix.
 *
 * OWNER + VIEWER use the credentials that the e2e mock backend already provides
 * (see e2e/helpers/auth.ts). SALES_STAFF / ACCOUNTANT blocks are written but
 * `test.fixme`-skipped until the mock seed exposes those logins; wire them by
 * adding loginAsSales / loginAsAccountant to helpers/auth.ts.
 */
import { expect, test } from '@playwright/test';
import { loginAsAccountant, loginAsOwner, loginAsSales, loginAsViewer } from '../helpers/auth';

test.describe('PJ-OWNER — full capability surface', () => {
  test('owner nav exposes journals, reports and user management', async ({ page }) => {
    await loginAsOwner(page);
    await page.goto('/');

    for (const path of ['/accounting/journals', '/reports', '/settings/users']) {
      await page.goto(path);
      await expect(page, `owner should reach ${path}`).toHaveURL(new RegExp(path.replace(/\//g, '\\/')));
      await expect(page.getByText(/access denied|forbidden|not authorised|403/i)).toHaveCount(0);
    }
  });

  test('owner can open the new-invoice form', async ({ page }) => {
    await loginAsOwner(page);
    await page.goto('/sales/new');
    await expect(page).toHaveURL(/\/sales\/new/);
    await expect(page).not.toHaveURL(/\/login/);
  });
});

test.describe('PJ-VIEWER — read-only, masters + reports hidden (BB-000422 / BUG-319)', () => {
  test('viewer landing renders the app shell, not a crash / error page', async ({ page }) => {
    await loginAsViewer(page);
    await page.goto('/');
    await expect.poll(async () => page.locator('#root').innerHTML(), { timeout: 20_000 }).not.toBe('');
    await expect(page).not.toHaveURL(/\/login/);
    await expect(page.getByText(/something went wrong|unexpected error/i)).toHaveCount(0);
  });

  test('viewer nav has no create / mutate entry points', async ({ page }) => {
    await loginAsViewer(page);
    await page.goto('/');
    await expect(page.getByRole('link', { name: /new invoice|new sale|new purchase/i })).toHaveCount(0);
    await expect(page.getByRole('button', { name: /new invoice|new sale|new purchase/i })).toHaveCount(0);
  });

  test('viewer never lands on a working invoice form', async ({ page }) => {
    await loginAsViewer(page);
    await page.goto('/sales/new');
    const onForm = await page.getByRole('button', { name: /save draft|complete invoice/i }).count();
    expect(onForm, 'viewer must not land on a working invoice form').toBe(0);
  });

  test('viewer sees no report export controls', async ({ page }) => {
    await loginAsViewer(page);
    await page.goto('/reports/profit-and-loss');
    // whatever the gate does (redirect / restricted panel), the report's own
    // action controls must not be reachable
    await expect(page.getByRole('button', { name: /export|download|xlsx|csv/i })).toHaveCount(0);
    const onReport = await page.getByRole('heading', { name: /profit *(&|and) *loss/i }).count();
    expect(onReport, 'viewer must not see the P&L report itself').toBe(0);
  });
});

test.describe('PJ-SALES — POS + invoices only', () => {
  test('sales staff can open the invoice form and POS', async ({ page }) => {
    await loginAsSales(page);
    for (const path of ['/sales/new', '/pos']) {
      await page.goto(path);
      await expect(page).toHaveURL(new RegExp(path.replace(/\//g, '\\/')));
      await expect(page).not.toHaveURL(/\/login/);
      await expect(page.getByText(/access denied|forbidden|no access|403/i)).toHaveCount(0);
    }
  });

  test('sales staff cannot post a journal or invite a user', async ({ page }) => {
    await loginAsSales(page);
    await page.goto('/accounting/journals');
    // no journal-mutate control, whether the route redirects or shows a panel
    await expect(page.getByRole('button', { name: /new journal|post journal|add entry/i })).toHaveCount(0);
    await page.goto('/settings/users');
    await expect(page.getByRole('button', { name: /invite user|add user/i })).toHaveCount(0);
  });
});

test.describe('PJ-ACCT — books + reports, no sales creation', () => {
  test('accountant reaches journals + reports', async ({ page }) => {
    await loginAsAccountant(page);
    for (const path of ['/accounting/journals', '/reports']) {
      await page.goto(path);
      await expect(page).toHaveURL(new RegExp(path.replace(/\//g, '\\/')));
      await expect(page.getByText(/access denied|forbidden|no access|403/i)).toHaveCount(0);
    }
  });

  test('accountant cannot land on a working new-invoice form', async ({ page }) => {
    await loginAsAccountant(page);
    await page.goto('/sales/new');
    const onForm = await page.getByRole('button', { name: /save draft|complete invoice/i }).count();
    expect(onForm, 'accountant must not get a working invoice form').toBe(0);
  });
});

// QOS-0025 (UX-002 regression): a non-owner first load must not trigger a burst
// of 403s from an eager query the role is not entitled to run.
for (const role of ['sales', 'accountant', 'viewer'] as const) {
  test(`${role} first load produces no 403 responses (UX-002)`, async ({ page }) => {
    const forbidden: string[] = [];
    page.on('response', (r) => {
      if (r.status() === 403) forbidden.push(`${r.request().method()} ${new URL(r.url()).pathname}`);
    });
    const login = { sales: loginAsSales, accountant: loginAsAccountant, viewer: loginAsViewer }[role];
    await login(page);
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    expect(forbidden, `${role} saw 403s on first load: ${forbidden.join(', ')}`).toEqual([]);
  });
}
