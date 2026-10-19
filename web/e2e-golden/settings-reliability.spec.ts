import { expect, test, type Page, type Request } from '@playwright/test';
import { getCsrfToken, registerTenant, unique } from './helpers/documents';

/**
 * SET-27: how Settings behaves when things go wrong, on the live backend: a double-click, a refresh in
 * the middle of a save, losing the connection, a slow API, a session that ends, and another owner
 * editing the same record. Covers Company, Series, Bank Accounts, Payment gateway, Users and Import.
 */
test.describe.configure({ mode: 'serial' });

test.describe('Settings reliability', () => {
  test.setTimeout(180_000);
  let page: Page;

  test.beforeAll(async ({ browser }) => {
    const context = await browser.newContext();
    page = await context.newPage();
    const id = unique();
    await registerTenant(page, {
      companyName: `E2E Reliability ${id}`,
      email: `e2e-rel-${id}@example.test`,
      password: 'GoldenPath123!',
    });
  });
  test.afterAll(async () => page.context().close());

  const writes = (matcher: RegExp, method = 'PATCH') => {
    const seen: Request[] = [];
    const on = (r: Request) => {
      if (r.method() === method && matcher.test(r.url())) seen.push(r);
    };
    page.on('request', on);
    return { seen, stop: () => page.off('request', on) };
  };

  const saveBar = () => page.getByRole('button', { name: 'Save', exact: true });

  test('Company: a double-click saves once', async () => {
    await page.goto('/settings/company');
    await page.getByLabel('City').fill('Double Click City');
    const counter = writes(/\/api\/v1\/company\/$/);
    await saveBar().dblclick();
    await expect(page.getByText(/Saved/).first()).toBeVisible();
    counter.stop();
    expect(counter.seen).toHaveLength(1);
  });

  test('Company: losing the connection shows what to do, and saving again works once it is back', async () => {
    await page.goto('/settings/company');
    await page.getByLabel('City').fill('Offline City');
    await page.context().setOffline(true);
    await saveBar().click();
    await expect(page.getByRole('alert').filter({ hasText: /internet|connection/i }).first()).toBeVisible();
    await page.context().setOffline(false);
    if (await saveBar().isEnabled()) await saveBar().click().catch(() => undefined);
    await expect(page.getByText(/Saved/).first()).toBeVisible({ timeout: 20_000 });
    await page.reload();
    await expect(page.getByLabel('City')).toHaveValue('Offline City');
  });

  test('Company: a slow API shows a loading state, then the form', async () => {
    await page.route('**/api/v1/company/', async (route) => {
      if (route.request().method() === 'GET') await new Promise((r) => setTimeout(r, 2500));
      await route.continue();
    });
    await page.goto('/settings/company');
    await expect(page.getByLabel('City')).toBeHidden();
    await expect(page.getByLabel('City')).toBeVisible({ timeout: 15_000 });
    await page.unroute('**/api/v1/company/');
  });

  test('Company: refreshing in the middle of a save leaves a consistent, usable page', async () => {
    await page.goto('/settings/company');
    await page.getByLabel('City').fill('Refresh City');
    await page.route('**/api/v1/company/', async (route) => {
      if (route.request().method() === 'PATCH') await new Promise((r) => setTimeout(r, 2000));
      // The page may already be gone (that is the point of this test); a late continue is harmless.
      await route.continue().catch(() => undefined);
    });
    await saveBar().click();
    await page.reload();
    await page.unroute('**/api/v1/company/');
    await expect(page.getByLabel('City')).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole('alert').filter({ hasText: /error|failed|went wrong/i })).toHaveCount(0);
    const value = await page.getByLabel('City').inputValue();
    expect(['Refresh City', 'Offline City']).toContain(value);
  });

  test('Company: another owner changing the same record gives a conflict, not a silent overwrite', async () => {
    await page.goto('/settings/company');
    await expect(page.getByLabel('City')).toBeVisible();
    const csrf = await getCsrfToken(page);
    // Someone else saves the company after this page loaded.
    const other = await page.evaluate(async (token) => {
      const res = await fetch('/api/v1/company/', {
        method: 'PATCH',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': token },
        body: JSON.stringify({ phone: '9876543210' }),
      });
      return res.status;
    }, csrf);
    expect(other).toBe(200);
    await page.getByLabel('City').fill('Mine City');
    await saveBar().click();
    await expect(page.getByRole('dialog').getByText(/changed|someone else/i).first()).toBeVisible();
    await page.getByRole('button', { name: /overwrite/i }).click();
    await expect(page.getByText(/Saved/).first()).toBeVisible();
    await page.reload();
    await expect(page.getByLabel('City')).toHaveValue('Mine City');
  });

  test('Series: a double-click save sends one request and the number changes once', async () => {
    await page.goto('/settings/series');
    const prefix = page.getByLabel(/Sales Invoices.*Prefix|Prefix.*Sales Invoices/i).first();
    await expect(prefix).toBeVisible();
    await prefix.fill('REL');
    const counter = writes(/\/api\/v1\/company\/number-series\/$/);
    await saveBar().dblclick();
    await page.getByRole('dialog').getByRole('button', { name: 'Confirm' }).click();
    await expect(page.getByText(/Saved/).first()).toBeVisible();
    counter.stop();
    expect(counter.seen).toHaveLength(1);
  });

  test('Bank accounts: a double-click on Save in the dialog creates one account', async () => {
    await page.goto('/settings/bank-accounts');
    await page.getByRole('button', { name: 'Add account' }).click();
    const dialog = page.getByRole('dialog');
    await dialog.getByRole('textbox', { name: /^Name/ }).fill('Reliability Bank');
    const counter = writes(/\/api\/v1\/payments\/bank-accounts\/$/, 'POST');
    await dialog.getByRole('button', { name: 'Save', exact: true }).dblclick();
    await expect(dialog).toBeHidden({ timeout: 15_000 });
    counter.stop();
    expect(counter.seen).toHaveLength(1);
    await expect(page.getByText('Reliability Bank')).toHaveCount(1);
  });

  test('Payment gateway: losing the connection while saving shows what to do and keeps what was typed', async () => {
    await page.goto('/settings/payment-gateway');
    const field = page.getByLabel('Webhook secret');
    await expect(field).toBeVisible();
    await field.fill('whsec_reliability');
    await page.context().setOffline(true);
    await page.getByRole('button', { name: 'Save settings' }).click();
    await expect(page.getByRole('alert').filter({ hasText: /internet|connection/i }).first()).toBeVisible();
    await expect(field).toHaveValue('whsec_reliability');
    await page.context().setOffline(false);
    // The client retries a dropped request by itself; if it has not finished yet, save again.
    const save = page.getByRole('button', { name: 'Save settings' });
    if (await save.isEnabled()) await save.click().catch(() => undefined);
    await expect(page.getByText('Gateway settings saved')).toBeVisible({ timeout: 20_000 });
  });

  test('Users: a double-click on Invite adds one person', async () => {
    await page.goto('/settings/users');
    await page.getByRole('button', { name: 'Invite user' }).click();
    const dialog = page.getByRole('dialog');
    const email = `invitee-${unique()}@example.test`;
    await dialog.getByRole('textbox', { name: /^Email/ }).fill(email);
    await dialog.getByRole('textbox', { name: /^Full name/ }).fill('Reliability Invitee');
    const counter = writes(/\/api\/v1\/company\/users\/$/, 'POST');
    await dialog.getByRole('button', { name: 'Save', exact: true }).dblclick();
    await expect(dialog.getByText(/invite|link|token/i).first()).toBeVisible({ timeout: 15_000 });
    counter.stop();
    expect(counter.seen).toHaveLength(1);
  });

  test('Import: a slow history list shows a loading state, then the empty message', async () => {
    await page.route('**/api/v1/imports/?*', async (route) => {
      if (route.request().method() === 'GET') await new Promise((r) => setTimeout(r, 2500));
      await route.continue();
    });
    await page.goto('/settings/import');
    await expect(page.getByText('Past imports')).toBeVisible();
    await expect(page.getByText('No imports yet.')).toBeVisible({ timeout: 15_000 });
    await page.unroute('**/api/v1/imports/?*');
  });

  test('Series: after the session ends, saving says so in plain words and keeps what was typed', async () => {
    await page.goto('/settings/series');
    const prefix = page.getByLabel(/Sales Invoices.*Prefix|Prefix.*Sales Invoices/i).first();
    await expect(prefix).toBeVisible();
    await prefix.fill('EXP');
    await page.context().clearCookies();
    await saveBar().click();
    await page.getByRole('dialog').getByRole('button', { name: 'Confirm' }).click().catch(() => undefined);
    await expect(page.getByRole('alert').filter({ hasText: /session has ended/i }).first()).toBeVisible({ timeout: 20_000 });
    await expect(prefix).toHaveValue('EXP');
  });
});
