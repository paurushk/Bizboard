import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';
import {
  addStockAdjustment,
  createCustomer,
  createProduct,
  getCsrfToken,
  registerTenant,
  unique,
} from './helpers/documents';

/**
 * DAN-16/17: Needs attention against the live backend. An overdue invoice becomes one customer row;
 * it can be snoozed, reopened, dismissed and undone, shows on the dashboard, and the page holds up
 * on a phone. Live Django, no mocks.
 */

function rows(body: unknown): Array<Record<string, unknown>> {
  const b = body as { data?: { results?: unknown[] } | unknown[]; results?: unknown[] };
  const list = (Array.isArray(b?.data) ? b.data : b?.data && 'results' in b.data ? b.data.results : b?.results) ?? [];
  return list as Array<Record<string, unknown>>;
}

async function api(page: Page, method: 'get' | 'post', url: string, data?: Record<string, unknown>) {
  const token = await getCsrfToken(page);
  const res = await page.request[method](url, {
    data,
    headers: { 'X-CSRFToken': token, Referer: page.url() || 'http://127.0.0.1/' },
  });
  expect(res.ok(), `${method} ${url} -> ${res.status()} ${await res.text()}`).toBeTruthy();
  return res.json();
}

async function overdueInvoice(page: Page, customerName: string, sku: string, daysOverdue = 40) {
  const customers = rows(await api(page, 'get', `/api/v1/customers/?search=${encodeURIComponent(customerName)}`));
  const products = rows(await api(page, 'get', `/api/v1/products/?search=${encodeURIComponent(sku)}`));
  const customer = customers.find((c) => c.name === customerName);
  const product = products.find((p) => p.sku === sku);
  expect(customer && product).toBeTruthy();
  const due = new Date(Date.now() - daysOverdue * 24 * 3600 * 1000).toISOString().slice(0, 10);
  const created = await api(page, 'post', '/api/v1/sales/invoices/', {
    customer: customer!.id,
    invoice_type: 'NON_GST',
    invoice_date: due,
    due_date: due,
    items: [{ product: product!.id, quantity: '1', unit_price: '500' }],
  });
  const id = (created.data ?? created).id;
  await api(page, 'post', `/api/v1/sales/invoices/${id}/complete/`, {});
}

test('Needs attention: overdue customer row can be snoozed, reopened, dismissed and undone', async ({ page }) => {
  test.setTimeout(240_000);
  const id = unique();
  const customerName = `Attn Cust ${id}`;
  const sku = `ATTN-${id}`;
  await registerTenant(page, { companyName: `E2E Attention ${id}`, email: `e2e-attn-${id}@example.test`, password: 'GoldenPath123!' });
  await createProduct(page, { name: `Attn Widget ${id}`, sku, sellingPrice: '500', purchasePrice: '300' });
  await addStockAdjustment(page, { sku, quantity: '10' });
  await createCustomer(page, { name: customerName });
  await overdueInvoice(page, customerName, sku);

  // The dashboard preview shows it, and the health chip no longer says "Needs attention".
  await page.goto('/');
  await expect(page.getByText(new RegExp(customerName)).first()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(/Needs attention · open/)).toHaveCount(0);

  await page.goto('/attention');
  const row = page.getByRole('row').filter({ hasText: customerName });
  await expect(row).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole('columnheader', { name: 'Amount involved' })).toBeVisible();
  await expect(row).toContainText(/overdue/i);
  await expect(row).toContainText(/₹\s?500/);
  await page.screenshot({ path: 'test-results/attention-desktop.png', fullPage: true });

  // Snooze, then find it under Snoozed, reopen it.
  await row.getByRole('button', { name: /snooze/i }).click();
  await page.getByLabel('Reason').fill('Customer promised Friday');
  await page.getByRole('dialog').getByRole('button', { name: /snooze/i }).click();
  await expect(page.getByRole('row').filter({ hasText: customerName })).toHaveCount(0, { timeout: 15_000 });
  await page.getByRole('tab', { name: /snoozed/i }).click();
  const snoozed = page.getByRole('row').filter({ hasText: customerName });
  await expect(snoozed).toBeVisible({ timeout: 15_000 });
  await expect(snoozed).toContainText('Customer promised Friday');
  await expect(snoozed).toContainText(/By E2E Tester on /);
  await snoozed.getByRole('button', { name: 'Reopen' }).click();
  await page.getByRole('tab', { name: /^open/i }).click();
  await expect(page.getByRole('row').filter({ hasText: customerName })).toBeVisible({ timeout: 15_000 });

  // Dismiss (a reason may be required for a critical row), then Undo from the toast.
  await page.getByRole('row').filter({ hasText: customerName }).getByRole('button', { name: 'Dismiss' }).click();
  const reason = page.getByRole('dialog').getByRole('textbox');
  if (await reason.isVisible().catch(() => false)) {
    await reason.fill('Settled in cash');
    await page.getByRole('dialog').getByRole('button', { name: 'Dismiss' }).click();
  }
  await expect(page.getByText('Dismissed.')).toBeVisible({ timeout: 15_000 });
  await page.getByRole('button', { name: 'Undo' }).click();
  await expect(page.getByRole('row').filter({ hasText: customerName })).toBeVisible({ timeout: 15_000 });

  // Hindi: tabs, column heading and the amount basis are translated.
  await page.getByRole('button', { name: 'हिंदी' }).click();
  await expect(page.getByRole('tab', { name: /स्थगित/ })).toBeVisible({ timeout: 15_000 });
  await expect(page.getByRole('columnheader', { name: 'शामिल राशि' })).toBeVisible();
  await expect(page.getByRole('row').filter({ hasText: customerName })).toContainText('बकाया');
  await page.screenshot({ path: 'test-results/attention-hindi.png', fullPage: true });
});

test('Needs attention holds up on a phone: cards, no sideways scroll, reachable actions', async ({ page }) => {
  test.setTimeout(240_000);
  const id = unique();
  const customerName = `Attn Phone ${id}`;
  const sku = `ATTP-${id}`;
  await registerTenant(page, { companyName: `E2E Attention Phone ${id}`, email: `e2e-attnp-${id}@example.test`, password: 'GoldenPath123!' });
  await createProduct(page, { name: `Attn Phone Widget ${id}`, sku, sellingPrice: '500', purchasePrice: '300' });
  await addStockAdjustment(page, { sku, quantity: '10' });
  await createCustomer(page, { name: customerName });
  await overdueInvoice(page, customerName, sku);

  await page.setViewportSize({ width: 375, height: 812 });
  for (const path of ['/attention', '/']) {
    await page.goto(path);
    await expect(page.getByText(new RegExp(customerName)).first()).toBeVisible({ timeout: 30_000 });
    await page.waitForLoadState('networkidle');
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    const offenders = overflow > 1
      ? await page.evaluate(() =>
          Array.from(document.querySelectorAll('body *'))
            .filter((el) => {
              if (el.getBoundingClientRect().right <= window.innerWidth + 1) return false;
              // Inside a scroll container the overflow is contained and is not the page's problem.
              for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) {
                const o = getComputedStyle(p).overflowX;
                if (o === 'auto' || o === 'scroll' || o === 'hidden') return false;
              }
              return true;
            })
            .slice(0, 6)
            .map((el) => `${el.tagName.toLowerCase()}.${String(el.className).slice(0, 60)} right=${Math.round(el.getBoundingClientRect().right)} text=${(el.textContent ?? '').slice(0, 30)}`),
        )
      : [];
    expect(overflow, `${path} scrolls sideways by ${overflow}px: ${offenders.join(' | ')}`).toBeLessThanOrEqual(1);
    await page.screenshot({ path: `test-results/attention-phone${path === '/' ? '-dashboard' : ''}.png`, fullPage: true });
  }
  await page.goto('/attention');
  await expect(page.getByRole('table')).toHaveCount(0);
  const card = page.getByRole('listitem').filter({ hasText: customerName });
  await expect(card).toBeVisible();
  const box = await card.getByRole('button', { name: 'Dismiss' }).boundingBox();
  expect(box?.height ?? 0).toBeGreaterThanOrEqual(43);
});

async function setUp(page: Page, label: string, daysOverdue: number) {
  const id = unique();
  const customerName = `Attn ${label} ${id}`;
  const sku = `ATT${label.slice(0, 2).toUpperCase()}-${id}`;
  await registerTenant(page, { companyName: `E2E Attention ${label} ${id}`, email: `e2e-attn-${label}-${id}@example.test`, password: 'GoldenPath123!' });
  await createProduct(page, { name: `Attn ${label} Widget ${id}`, sku, sellingPrice: '500', purchasePrice: '300' });
  await addStockAdjustment(page, { sku, quantity: '10' });
  await createCustomer(page, { name: customerName });
  await overdueInvoice(page, customerName, sku, daysOverdue);
  return customerName;
}

test('Needs attention: a critical row needs a reason to dismiss, and the page works from the keyboard', async ({ page }) => {
  test.setTimeout(240_000);
  const customerName = await setUp(page, 'Crit', 120);
  await page.goto('/attention');
  const row = page.getByRole('row').filter({ hasText: customerName });
  await expect(row).toBeVisible({ timeout: 30_000 });
  await expect(row).toContainText(/critical/i);

  // Dismiss on a critical row asks why; it stays disabled until there are three characters.
  await row.getByRole('button', { name: 'Dismiss' }).click();
  const confirm = page.getByRole('dialog').getByRole('button', { name: 'Dismiss' });
  await expect(confirm).toBeDisabled();
  await page.getByRole('dialog').getByRole('textbox').fill('ab');
  await expect(confirm).toBeDisabled();
  await page.getByRole('dialog').getByRole('textbox').fill('Paid in cash today');
  await expect(confirm).toBeEnabled();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).toBeHidden();

  // Keyboard only: focus Snooze, Enter opens the dialog, Escape closes it and puts focus back.
  const snooze = row.getByRole('button', { name: /snooze/i });
  await snooze.focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).toBeHidden();
  await expect(snooze).toBeFocused();
});

test('Needs attention: no colour-contrast or other serious accessibility problems, in English and Hindi', async ({ page }) => {
  test.setTimeout(240_000);
  const customerName = await setUp(page, 'Axe', 120);
  async function check(path: string, wait: () => Promise<void>) {
    await page.goto(path);
    await wait();
    await page.waitForLoadState('networkidle');
    const results = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa']).analyze();
    const blocking = results.violations.filter((v) => v.impact === 'critical' || v.impact === 'serious');
    expect(blocking.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(' ')).join(' | ')}`), path).toEqual([]);
  }
  const attention = async () => { await expect(page.getByText(new RegExp(customerName)).first()).toBeVisible({ timeout: 30_000 }); };
  await check('/attention', attention);
  await check('/', attention);
  await page.getByRole('button', { name: 'हिंदी' }).click();
  await check('/attention', attention);
  await check('/', attention);
});

test('Needs attention: when the network drops the page says so and keeps the last list', async ({ page, context }) => {
  test.setTimeout(240_000);
  const customerName = await setUp(page, 'Off', 40);
  await page.goto('/attention');
  await expect(page.getByRole('row').filter({ hasText: customerName })).toBeVisible({ timeout: 30_000 });
  await context.setOffline(true);
  // A new filter has no cached list, so the page has to ask the server and cannot.
  await page.getByLabel('Severity').click();
  await page.getByRole('option', { name: /warning/i }).click();
  // Offline: say so (or that the data may be out of date), keep the last list, never claim all clear.
  await expect(page.getByText(/You are offline|may be out of date/).first()).toBeVisible({ timeout: 40_000 });
  await expect(page.getByText('Nothing needs attention right now.')).toHaveCount(0);
  await expect(page.getByText('No items match these filters.')).toHaveCount(0);
  await context.setOffline(false);
  await expect(page.getByText(/You are offline|may be out of date/)).toBeHidden({ timeout: 60_000 });
  await expect(page.getByRole('row').filter({ hasText: customerName })).toBeVisible({ timeout: 30_000 });
});
