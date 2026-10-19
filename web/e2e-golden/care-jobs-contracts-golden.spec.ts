import { expect, test, type Page } from '@playwright/test';
import { createCustomer, getCsrfToken, registerTenant, unique } from './helpers/documents';
import { grantRolloutFlag } from './helpers/grantFlag';

// Customer care and Jobs & contracts journeys (plan QA-05). The records are arranged through the API so the
// run does not depend on every dialog; the browser then checks what a person sees on each screen.

const FLAGS = ['ENABLE_SUPPORT_TICKETS', 'ENABLE_COMPLAINTS', 'ENABLE_CONTRACTS', 'ENABLE_PROJECTS'];

async function post(page: Page, url: string, data: Record<string, unknown>) {
  const csrf = await getCsrfToken(page);
  const res = await page.request.post(url, { headers: { 'X-CSRFToken': csrf }, data });
  expect(res.ok(), `${url}: ${await res.text()}`).toBeTruthy();
  const body = await res.json();
  return (body?.data ?? body) as Record<string, unknown> & { id: number };
}

async function setup(page: Page, label: string) {
  const id = unique();
  const email = `e2e-care-${label}-${id}@example.test`;
  const customerName = `Care Customer ${id}`;
  await registerTenant(page, { companyName: `E2E Care ${id}`, email, password: 'GoldenPath123!' });
  for (const flag of FLAGS) grantRolloutFlag(email, flag);
  await createCustomer(page, { name: customerName });
  const list = await page.request.get('/api/v1/customers/?page_size=200');
  const body = await list.json();
  const rows = (body?.data?.results ?? body?.data ?? body?.results ?? []) as { id: number; name: string }[];
  const customer = rows.find((row) => row.name === customerName);
  expect(customer, 'the customer just created').toBeTruthy();
  return { id, customerName, customerId: customer!.id };
}

test('a support ticket moves from open to resolved and shows on its list', async ({ page }) => {
  test.setTimeout(150_000);
  const { customerId } = await setup(page, 'ticket');
  const ticket = await post(page, '/api/v1/support/tickets/', { customer: customerId, subject: 'Pump leaks', priority: 'MEDIUM' });
  await post(page, `/api/v1/support/tickets/${ticket.id}/transition/`, { status: 'IN_PROGRESS' });
  await post(page, `/api/v1/support/tickets/${ticket.id}/transition/`, { status: 'RESOLVED' });
  await page.goto('/support/tickets');
  await expect(page.getByText('Pump leaks').first()).toBeVisible({ timeout: 20_000 });
});

test('a customer complaint is logged and listed', async ({ page }) => {
  test.setTimeout(150_000);
  const { customerId } = await setup(page, 'complaint');
  await post(page, '/api/v1/complaints/', { customer: customerId, category: 'DAMAGED', description: 'Arrived broken' });
  await page.goto('/complaints');
  await expect(page.getByText('Arrived broken').first()).toBeVisible({ timeout: 20_000 });
});

test('a contract is created and listed', async ({ page }) => {
  test.setTimeout(150_000);
  const { customerId, customerName } = await setup(page, 'contract');
  const today = new Date();
  const iso = (offsetDays: number) => {
    const d = new Date(today.getTime() + offsetDays * 86_400_000);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  };
  await post(page, '/api/v1/contracts/', {
    customer: customerId, contract_type: 'AMC', start_date: iso(-30), end_date: iso(300), value: '1200.00', renewal_reminder_days: 30,
  });
  await page.goto('/contracts');
  await expect(page.getByText(customerName).first()).toBeVisible({ timeout: 20_000 });
});

test('the service quality page opens once a care module is on', async ({ page }) => {
  test.setTimeout(150_000);
  await setup(page, 'quality');
  await page.goto('/care/quality');
  await expect(page.getByRole('heading', { name: 'Service quality' })).toBeVisible({ timeout: 20_000 });
});
