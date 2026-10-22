import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';
import { getCsrfToken, registerTenant, unique } from './helpers/documents';
import { seedManufacturingDemo } from './helpers/grantFlag';

/**
 * Manufacturing against the live backend: a production day on the one-screen entry, the work order,
 * planning, quality, job work, the shop floor, reports, settings, and the PIN-signed tablet.
 * Live Django, no mocks. The demo set-up (recipes, work centre, operator) comes from
 * `manage.py seed_manufacturing_demo`, the same command a trainer would run.
 */

function watchErrors(page: Page) {
  const problems: string[] = [];
  page.on('pageerror', (e) => problems.push(`pageerror: ${e.message}`));
  page.on('console', (m) => {
    if (m.type() !== 'error') return;
    const text = m.text();
    // Failed network calls are asserted on separately; a favicon or font request is not a product problem.
    if (/favicon|Failed to load resource|net::ERR/.test(text)) return;
    problems.push(`console: ${text}`);
  });
  return problems;
}

async function open(page: Page, path: string, heading: string | RegExp) {
  await page.goto(path);
  await expect(page.getByRole('heading', { name: heading }).first()).toBeVisible({ timeout: 20_000 });
}

test('Manufacturing: a production day from the one-screen entry to the shop-floor tablet', async ({ page, browser }) => {
  test.setTimeout(300_000);
  const problems = watchErrors(page);
  const id = unique();
  const email = `e2e-mfg-${id}@example.test`;
  await registerTenant(page, { companyName: `E2E Mfg ${id}`, email, password: 'GoldenPath123!' });
  seedManufacturingDemo(email);
  // One full load, not a reload followed by another: two page boots race to rotate the same refresh cookie.
  await page.goto('/');
  await expect(page.getByRole('navigation', { name: 'Main navigation' })).toBeVisible({ timeout: 20_000 });

  // The menu offers the module and its sub-modules.
  await page.getByRole('navigation', { name: 'Main navigation' }).getByText('Manufacturing', { exact: true }).first().click();
  await expect(page.getByRole('link', { name: 'Quick production' }).first()).toBeVisible();
  await expect(page.getByRole('link', { name: 'Planning' }).first()).toBeVisible();

  // Quick production: pick the item, the screen says how many can be made, record it.
  await open(page, '/manufacturing/quick', 'Quick production');
  await page.getByLabel('What did you make?').click();
  await page.getByRole('option', { name: /Butter biscuits/ }).click();
  await expect(page.getByText('You can make now')).toBeVisible();
  await page.getByLabel('Quantity', { exact: true }).fill('10');
  await page.getByRole('button', { name: 'Record production' }).click();
  await expect(page.getByText(/Recorded WO-/)).toBeVisible({ timeout: 20_000 });

  // The order it made, with its material and cost.
  await open(page, '/manufacturing/work-orders', 'Work Orders');
  await page.getByRole('link', { name: 'Details' }).first().click();
  await expect(page.getByRole('tab', { name: 'Overview' })).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText('Planned', { exact: true }).first()).toBeVisible();
  await page.getByRole('tab', { name: 'Material' }).click();
  await expect(page.getByText('Flour (kg)').first()).toBeVisible();

  // A recipe opens with its versions, materials and steps.
  await open(page, '/manufacturing/boms', 'Bills of Material');
  await page.getByRole('link', { name: 'Open' }).first().click();
  await expect(page.getByRole('tab', { name: 'Materials' })).toBeVisible({ timeout: 20_000 });
  await page.getByRole('tab', { name: 'Full list and cost' }).click();
  await expect(page.getByText('Cost to make')).toBeVisible({ timeout: 20_000 });

  // The sub-modules each open on their first screen.
  await open(page, '/manufacturing/planning', 'Production planning');
  await expect(page.getByRole('tab', { name: 'Orders' })).toBeVisible();
  await open(page, '/manufacturing/quality', 'Quality');
  await page.getByRole('button', { name: 'New inspection' }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.getByRole('button', { name: 'Cancel' }).click();
  await open(page, '/manufacturing/job-work', 'Job work');
  await page.getByRole('combobox', { name: 'Job worker', exact: true }).click();
  await page.getByRole('option', { name: /Demo Packers/ }).click();
  await page.getByLabel('Work done').fill('Packing');
  await page.getByRole('button', { name: 'New job work order' }).click();
  await expect(page.getByRole('cell', { name: /JWO-|JW-/ }).first()).toBeVisible({ timeout: 20_000 });
  await open(page, '/manufacturing/shop-floor', 'Shop floor');
  await expect(page.getByRole('tab', { name: 'Job cards' })).toBeVisible();
  await open(page, '/manufacturing/reports', 'Manufacturing reports');
  await expect(page.getByText('Work in progress').first()).toBeVisible();

  // Settings show the tablet address; open it signed out and work as an operator.
  await open(page, '/manufacturing/settings', 'Manufacturing settings');
  const address = await page.getByLabel('Shop-floor tablet address').inputValue();
  expect(address).toMatch(/\/floor\?company=\d+/);
  const tablet = await (await browser.newContext()).newPage();
  const tabletProblems = watchErrors(tablet);
  await tablet.goto(address);
  await tablet.getByLabel('Operator code').fill('DEMO1');
  await tablet.getByLabel('PIN').fill('0000');
  await tablet.getByRole('button', { name: 'Sign in' }).click();
  await expect(tablet.getByText(/Wrong code or PIN/i)).toBeVisible({ timeout: 15_000 });
  await tablet.getByLabel('PIN').fill('2468');
  await tablet.getByRole('button', { name: 'Sign in' }).click();
  await expect(tablet.getByText('Hello, Demo operator')).toBeVisible({ timeout: 15_000 });
  await expect(tablet.getByText('No jobs waiting for you right now.')).toBeVisible();
  await tablet.getByRole('button', { name: 'Sign out' }).click();
  await expect(tablet.getByRole('button', { name: 'Sign in' })).toBeVisible();

  expect(problems, problems.join('\n')).toEqual([]);
  expect(tabletProblems, tabletProblems.join('\n')).toEqual([]);
});

test('Manufacturing: the pages have no serious accessibility problems', async ({ page }) => {
  test.setTimeout(240_000);
  const id = unique();
  const email = `e2e-mfg-a11y-${id}@example.test`;
  await registerTenant(page, { companyName: `E2E Mfg A11y ${id}`, email, password: 'GoldenPath123!' });
  seedManufacturingDemo(email);
  for (const [path, heading] of [
    ['/manufacturing/quick', 'Quick production'],
    ['/manufacturing/planning', 'Production planning'],
    ['/manufacturing/quality', 'Quality'],
    ['/manufacturing/settings', 'Manufacturing settings'],
  ] as const) {
    await open(page, path, heading);
    const results = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa']).analyze();
    const serious = results.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical');
    expect(serious.map((v) => `${path}: ${v.id} ${v.help}`), `${path}`).toEqual([]);
  }
});

test('Manufacturing: a work order through issue, return, output and close in the browser', async ({ page }) => {
  test.setTimeout(300_000);
  const problems = watchErrors(page);
  const id = unique();
  const email = `e2e-mfg-wo-${id}@example.test`;
  await registerTenant(page, { companyName: `E2E Mfg WO ${id}`, email, password: 'GoldenPath123!' });
  seedManufacturingDemo(email);
  await page.goto('/');
  await expect(page.getByRole('navigation', { name: 'Main navigation' })).toBeVisible({ timeout: 20_000 });

  // Set the order up through the API (the screens for that are the older work order list); the documents are done in the browser.
  const token = await getCsrfToken(page);
  const headers = { 'X-CSRFToken': token, Referer: page.url() };
  const boms = await (await page.request.get('/api/v1/manufacturing/boms/?status=ACTIVE')).json();
  const rows = (boms.data?.results ?? boms.data) as Array<{ id: number; name: string }>;
  const bom = rows.find((b) => /biscuit/i.test(b.name));
  expect(bom).toBeTruthy();
  const created = await (await page.request.post('/api/v1/manufacturing/work-orders/', { data: { bom: bom!.id, qty: '10' }, headers })).json();
  const woId = (created.data ?? created).id as number;
  const released = await page.request.post(`/api/v1/manufacturing/work-orders/${woId}/release/`, { data: {}, headers });
  expect(released.ok(), await released.text()).toBeTruthy();

  await open(page, `/manufacturing/work-orders/${woId}`, /WO-/);
  await page.getByRole('tab', { name: 'Material' }).click();
  await page.getByRole('button', { name: 'Fill in what is left' }).click();
  await page.getByRole('button', { name: 'Issue material' }).click();
  await expect(page.getByRole('cell', { name: /MI-/ })).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText('Posted').first()).toBeVisible();

  await page.getByRole('tab', { name: 'Returns' }).click();
  await page.getByLabel('Quantity').first().fill('0.1');
  await page.getByRole('button', { name: 'Return to stock' }).click();
  await expect(page.getByRole('cell', { name: /MR-/ })).toBeVisible({ timeout: 20_000 });

  await page.getByRole('tab', { name: 'Output' }).click();
  await page.getByLabel('Good', { exact: true }).fill('10');
  await page.getByLabel('Last output').check();
  await page.getByRole('button', { name: 'Record output' }).click();
  await expect(page.getByRole('cell', { name: /PR-/ })).toBeVisible({ timeout: 20_000 });

  // The last output finishes the order; closing it settles the cost and the order shows what it cost.
  await page.getByRole('tab', { name: 'Overview' }).click();
  await expect(page.getByText('Done', { exact: true }).first()).toBeVisible({ timeout: 20_000 });
  await page.getByRole('button', { name: 'Close the work order' }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Confirm' }).click();
  await expect(page.getByText('Closed', { exact: true }).first()).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText('Value of output')).toBeVisible();

  // The print sheet opens as its own page with no money on it.
  const popup = page.waitForEvent('popup');
  await page.getByRole('button', { name: 'Print' }).first().click();
  const sheet = await popup;
  await expect(sheet.getByText('Checked by')).toBeVisible({ timeout: 15_000 });
  expect(await sheet.content()).not.toContain('₹');

  expect(problems, problems.join(String.fromCharCode(10))).toEqual([]);
});

test('Manufacturing: a made batch is held for its final check and released by the inspection', async ({ page }) => {
  test.setTimeout(300_000);
  const problems = watchErrors(page);
  const id = unique();
  const email = `e2e-mfg-q-${id}@example.test`;
  await registerTenant(page, { companyName: `E2E Mfg Quality ${id}`, email, password: 'GoldenPath123!' });
  seedManufacturingDemo(email);
  await page.goto('/');
  await expect(page.getByRole('navigation', { name: 'Main navigation' })).toBeVisible({ timeout: 20_000 });

  // A final-check list for the biscuits (set up through the API; the list editor has its own unit tests).
  const token = await getCsrfToken(page);
  const headers = { 'X-CSRFToken': token, Referer: page.url() };
  const boms = await (await page.request.get('/api/v1/manufacturing/boms/?status=ACTIVE')).json();
  const rows = (boms.data?.results ?? boms.data) as Array<{ id: number; name: string; product: number }>;
  const bom = rows.find((b) => /biscuit/i.test(b.name));
  expect(bom).toBeTruthy();
  const made = await page.request.post('/api/v1/quality/templates/', {
    data: {
      name: 'Final biscuit check', stage: 'FINAL', product: bom!.product, sampleSize: 1,
      parameters: [{ name: 'Weight', kind: 'NUMERIC', minValue: '9', maxValue: '11', unit: 'g', mandatory: true }],
    },
    headers,
  });
  expect(made.ok(), await made.text()).toBeTruthy();

  // Producing the batch puts it on hold and opens the check.
  await open(page, '/manufacturing/quick', 'Quick production');
  await page.getByLabel('What did you make?').click();
  await page.getByRole('option', { name: /Butter biscuits/ }).click();
  await page.getByLabel('Quantity', { exact: true }).fill('10');
  await page.getByLabel('Batch number').fill('QH-1');
  await page.getByRole('button', { name: 'Record production' }).click();
  await expect(page.getByText(/Recorded WO-/)).toBeVisible({ timeout: 20_000 });
  const held = await (await page.request.get('/api/v1/manufacturing/batches/?q=QH-1')).json();
  expect((held.data?.results ?? held.results)[0].qualityStatus).toBe('HOLD');

  await open(page, '/manufacturing/quality', 'Quality');
  const row = page.getByRole('row', { name: /QH-1/ });
  await expect(row).toBeVisible({ timeout: 20_000 });
  await expect(row.getByText('Draft')).toBeVisible();
  await row.click();
  const dialog = page.getByRole('dialog');
  await expect(dialog.getByText('Weight *')).toBeVisible({ timeout: 20_000 });

  // A weight outside the range fails the check; a good weight passes it and releases the batch.
  await dialog.getByRole('textbox').first().fill('12.5');
  await dialog.getByRole('button', { name: 'Save results' }).click();
  await expect(dialog.getByText('Fail').first()).toBeVisible({ timeout: 20_000 });
  await dialog.getByRole('textbox').first().fill('10');
  await dialog.getByRole('button', { name: 'Save results' }).click();
  await expect(dialog.getByText('Pass').first()).toBeVisible({ timeout: 20_000 });
  await dialog.getByRole('button', { name: 'Finish inspection' }).click();
  await expect(dialog).toBeHidden({ timeout: 20_000 });
  await expect(page.getByRole('row', { name: /QH-1/ }).getByText('Done')).toBeVisible({ timeout: 20_000 });
  const released = await (await page.request.get('/api/v1/manufacturing/batches/?q=QH-1')).json();
  expect((released.data?.results ?? released.results)[0].qualityStatus).toBe('RELEASED');

  expect(problems, problems.join('\n')).toEqual([]);
});

test('Manufacturing: goods go to a job worker with a challan and come back with the work done', async ({ page }) => {
  test.setTimeout(300_000);
  const problems = watchErrors(page);
  const id = unique();
  const email = `e2e-mfg-jw-${id}@example.test`;
  await registerTenant(page, { companyName: `E2E Mfg JobWork ${id}`, email, password: 'GoldenPath123!' });
  seedManufacturingDemo(email);
  await page.goto('/');
  await expect(page.getByRole('navigation', { name: 'Main navigation' })).toBeVisible({ timeout: 20_000 });

  await open(page, '/manufacturing/job-work', 'Job work');
  await page.getByRole('combobox', { name: 'Job worker', exact: true }).click();
  await page.getByRole('option', { name: /Demo Packers/ }).click();
  await page.getByLabel('Work done').fill('Packing');
  await page.getByRole('button', { name: 'New job work order' }).click();
  await expect(page.getByRole('cell', { name: /JWO-/ }).first()).toBeVisible({ timeout: 20_000 });

  // Send twenty gift boxes out with a challan.
  await page.getByRole('tab', { name: 'Challans' }).click();
  await page.getByRole('combobox', { name: 'Job work order' }).click();
  await page.getByRole('option', { name: /JWO-.*Demo Packers/ }).click();
  await page.getByLabel('Item').first().click();
  await page.getByRole('option', { name: /Gift box/ }).click();
  await page.getByLabel('Quantity', { exact: true }).first().fill('20');
  await page.getByRole('button', { name: 'Send out with challan' }).click();
  await expect(page.getByRole('cell', { name: /JWC-/ }).first()).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText(/Gift box 20 \(Still out 20\)/)).toBeVisible();

  // They show as held by the job worker.
  await page.getByRole('tab', { name: 'Who has what' }).click();
  await expect(page.getByRole('cell', { name: 'Demo Packers' }).first()).toBeVisible({ timeout: 20_000 });
  await expect(page.getByRole('cell', { name: 'Gift box' }).first()).toBeVisible();

  // Eighteen come back finished with the charge; two come back untouched. Nothing is left outstanding.
  await page.getByRole('tab', { name: 'Goods back' }).click();
  await page.getByRole('combobox', { name: 'Job work order' }).click();
  await page.getByRole('option', { name: /JWO-.*Demo Packers/ }).click();
  await page.getByLabel('Item', { exact: true }).first().click();
  await page.getByRole('option', { name: /Gift box/ }).click();
  await page.getByLabel('Quantity', { exact: true }).first().fill('18');
  await page.getByLabel('Material used', { exact: true }).first().click();
  await page.getByRole('option', { name: /Gift box/ }).click();
  await page.getByLabel('How much material was used').fill('18');
  await page.getByLabel('Job work charge').fill('90');
  await page.getByRole('button', { name: 'Record the return' }).click();
  await expect(page.getByRole('cell', { name: /JWR-/ }).first()).toBeVisible({ timeout: 20_000 });

  await page.getByRole('combobox', { name: 'Job work order' }).click();
  await page.getByRole('option', { name: /JWO-.*Demo Packers/ }).click();
  await page.getByRole('combobox', { name: 'What came back' }).click();
  await page.getByRole('option', { name: 'Returned untouched' }).click();
  await page.getByLabel('Item', { exact: true }).first().click();
  await page.getByRole('option', { name: /Gift box/ }).click();
  await page.getByLabel('Quantity', { exact: true }).first().fill('2');
  await page.getByRole('button', { name: 'Record the return' }).click();
  await expect(page.getByRole('cell', { name: /JWR-/ })).toHaveCount(2, { timeout: 20_000 });

  await page.getByRole('tab', { name: 'Who has what' }).click();
  await expect(page.getByRole('cell', { name: 'Gift box' })).toHaveCount(0, { timeout: 20_000 });

  // With everything accounted for the order can be closed.
  await page.getByRole('tab', { name: 'Orders' }).click();
  await page.getByRole('button', { name: 'Close', exact: true }).first().click();
  await expect(page.getByRole('button', { name: 'Close', exact: true })).toHaveCount(0, { timeout: 20_000 });

  expect(problems, problems.join('\n')).toEqual([]);
});

// --- journeys for the second pass: re-pricing, approval, an outside step, the tablet without a signal ---------------------------

async function setUp(page: Page, tag: string) {
  const id = unique();
  const email = `e2e-mfg-${tag}-${id}@example.test`;
  await registerTenant(page, { companyName: `E2E Mfg ${tag} ${id}`, email, password: 'GoldenPath123!' });
  seedManufacturingDemo(email);
  await page.goto('/');
  await expect(page.getByRole('navigation', { name: 'Main navigation' })).toBeVisible({ timeout: 20_000 });
  const token = await getCsrfToken(page);
  return { headers: { 'X-CSRFToken': token, Referer: page.url() } };
}

async function api(page: Page, method: 'get' | 'post' | 'put', url: string, headers: Record<string, string>, data?: unknown) {
  const res = method === 'get' ? await page.request.get(url) : await page.request[method](url, { data: data ?? {}, headers });
  expect(res.ok(), `${method} ${url}: ${await res.text()}`).toBeTruthy();
  const json = await res.json();
  return (json.data ?? json) as any; // eslint-disable-line @typescript-eslint/no-explicit-any
}

const rowsOf = (d: any) => (d?.results ?? d) as any[]; // eslint-disable-line @typescript-eslint/no-explicit-any

test('Manufacturing: stock is re-priced to a new standard cost, previewed first, and the re-pricing can be reversed', async ({ page }) => {
  test.setTimeout(300_000);
  const problems = watchErrors(page);
  const { headers } = await setUp(page, 'reprice');
  const products = rowsOf(await api(page, 'get', '/api/v1/products/?search=Flour', headers));
  const flour = products.find((p) => /Flour/.test(p.name));
  expect(flour).toBeTruthy();
  await api(page, 'post', '/api/v1/manufacturing/standard-costs/', headers, { product: flour.id, effectiveFrom: '2026-01-01', material: '33' });

  await open(page, '/manufacturing/reports', 'Manufacturing reports');
  await page.getByRole('tab', { name: 'Standard costs' }).click();
  await expect(page.getByRole('heading', { name: 'Re-price stock to the standard cost' })).toBeVisible({ timeout: 20_000 });
  await page.getByRole('button', { name: 'Preview', exact: true }).click();
  await expect(page.getByRole('cell', { name: 'Flour (kg)' }).first()).toBeVisible({ timeout: 20_000 });
  // nothing has moved yet: the history is empty until it is posted
  await expect(page.getByText('Earlier re-pricing')).toBeVisible();
  await page.getByRole('button', { name: 'Post the re-pricing' }).click();
  await expect(page.getByRole('cell', { name: /^SR-/ }).first()).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText('Posted', { exact: true }).first()).toBeVisible();

  await page.getByRole('button', { name: 'Reverse', exact: true }).first().click();
  const dialog = page.getByRole('dialog');
  await dialog.getByRole('textbox').fill('wrong standard');
  await dialog.getByRole('button', { name: 'Confirm' }).click();
  await expect(page.getByText('Reversed', { exact: true }).first()).toBeVisible({ timeout: 20_000 });
  expect(problems, problems.join('\n')).toEqual([]);
});

test('Manufacturing: extra material waits for a manager, who approves it from the work order', async ({ page }) => {
  test.setTimeout(300_000);
  const problems = watchErrors(page);
  const { headers } = await setUp(page, 'approve');
  const boms = rowsOf(await api(page, 'get', '/api/v1/manufacturing/boms/?status=ACTIVE', headers));
  const bom = boms.find((b) => /biscuit/i.test(b.name));
  const wo = await api(page, 'post', '/api/v1/manufacturing/work-orders/', headers, { bom: bom.id, qty: '10' });
  await api(page, 'post', `/api/v1/manufacturing/work-orders/${wo.id}/release/`, headers);
  const detail = await api(page, 'get', `/api/v1/manufacturing/work-orders/${wo.id}/`, headers);
  const line = detail.componentLines.find((l: any) => /Gift box/i.test(l.componentName ?? '')) ?? detail.componentLines[0]; // eslint-disable-line @typescript-eslint/no-explicit-any
  const draft = await api(page, 'post', '/api/v1/manufacturing/material-issues/', headers, {
    workOrder: wo.id, lines: [{ woLine: line.id, qty: String(Number(line.qty) * 3), extraReason: 'Spilt in the mixer' }],
  });
  await api(page, 'post', `/api/v1/manufacturing/material-issues/${draft.id}/request-approval/`, headers, { note: 'need it today' });

  await open(page, `/manufacturing/work-orders/${wo.id}`, /WO-/);
  await page.getByRole('tab', { name: 'Material' }).click();
  await expect(page.getByText('Waiting for a manager')).toBeVisible({ timeout: 20_000 });
  await page.getByRole('button', { name: 'Approve and post' }).click();
  await expect(page.getByText('Posted').first()).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText('Waiting for a manager')).toHaveCount(0);
  expect(problems, problems.join('\n')).toEqual([]);
});

test('Manufacturing: a step done outside is sent to the job worker from its job card', async ({ page }) => {
  test.setTimeout(300_000);
  const problems = watchErrors(page);
  const { headers } = await setUp(page, 'outside');
  const boms = rowsOf(await api(page, 'get', '/api/v1/manufacturing/boms/?status=ACTIVE', headers));
  const bom = boms.find((b) => /biscuit/i.test(b.name));
  const centre = rowsOf(await api(page, 'get', '/api/v1/manufacturing/work-centres/', headers))[0];
  const supplier = rowsOf(await api(page, 'get', '/api/v1/suppliers/?search=Demo', headers)).find((s) => /Demo Packers/.test(s.name));
  expect(supplier).toBeTruthy();
  const revised = await api(page, 'post', `/api/v1/manufacturing/boms/${bom.id}/revise/`, headers, { reason: 'plating moved outside' });
  await api(page, 'put', `/api/v1/manufacturing/boms/${revised.id}/routing/`, headers, {
    operations: [{ sequence: 10, name: 'Plating', workCentre: centre.id, isSubcontract: true, subcontractSupplier: supplier.id }],
  });
  await api(page, 'post', `/api/v1/manufacturing/boms/${revised.id}/activate/`, headers, { makeDefault: true });
  const wo = await api(page, 'post', '/api/v1/manufacturing/work-orders/', headers, { bom: revised.id, qty: '10' });
  await api(page, 'post', `/api/v1/manufacturing/work-orders/${wo.id}/release/`, headers);
  await api(page, 'post', '/api/v1/manufacturing/job-cards/create-for-order/', headers, { workOrder: wo.id });

  await open(page, '/manufacturing/shop-floor', 'Shop floor');
  await page.getByLabel('Status').click();
  await page.getByRole('option', { name: 'Planned' }).click();
  await page.getByRole('button', { name: 'Send to job worker' }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog.getByText(/Send "Plating" to a job worker/)).toBeVisible({ timeout: 20_000 });
  await dialog.getByRole('button', { name: 'Send to job worker' }).click();
  // sending starts the step, so it leaves the Planned list and shows under In progress
  await expect(page.getByText('Nothing here yet.')).toBeVisible({ timeout: 20_000 });
  await page.getByLabel('Status').click();
  await page.getByRole('option', { name: 'In progress' }).click();
  await expect(page.getByText('With the job worker').first()).toBeVisible({ timeout: 20_000 });

  await open(page, '/manufacturing/job-work', 'Job work');
  await page.getByRole('tab', { name: 'Challans' }).click();
  await expect(page.getByRole('cell', { name: /JWC-/ }).first()).toBeVisible({ timeout: 20_000 });
  expect(problems, problems.join('\n')).toEqual([]);
});

test('Manufacturing: the tablet keeps taps made with no signal and sends them when the signal is back', async ({ page, browser }) => {
  test.setTimeout(300_000);
  const problems = watchErrors(page);
  const { headers } = await setUp(page, 'offline');
  const boms = rowsOf(await api(page, 'get', '/api/v1/manufacturing/boms/?status=ACTIVE', headers));
  const bom = boms.find((b) => /biscuit/i.test(b.name));
  const wo = await api(page, 'post', '/api/v1/manufacturing/work-orders/', headers, { bom: bom.id, qty: '10' });
  await api(page, 'post', `/api/v1/manufacturing/work-orders/${wo.id}/release/`, headers);
  const cards = await api(page, 'post', '/api/v1/manufacturing/job-cards/create-for-order/', headers, { workOrder: wo.id });
  const cardId = (cards.results ?? cards)[0].id;

  await open(page, '/manufacturing/settings', 'Manufacturing settings');
  const address = await page.getByLabel('Shop-floor tablet address').inputValue();

  const context = await browser.newContext();
  const tablet = await context.newPage();
  const tabletProblems = watchErrors(tablet);
  await tablet.goto(address);
  await tablet.getByLabel('Operator code').fill('DEMO1');
  await tablet.getByLabel('PIN').fill('2468');
  await tablet.getByRole('button', { name: 'Sign in' }).click();
  await expect(tablet.getByText('Hello, Demo operator')).toBeVisible({ timeout: 15_000 });
  await expect(tablet.getByText(/Mix and bake/)).toBeVisible();

  await context.setOffline(true);
  await tablet.getByRole('button', { name: 'Start' }).click();
  await expect(tablet.getByText(/Saved on this tablet/)).toBeVisible({ timeout: 15_000 });
  await expect(tablet.getByText(/1 taps are saved/)).toBeVisible();
  await expect(tablet.getByRole('button', { name: 'Pause' })).toBeVisible();          // the job reads as running at once
  const before = await api(page, 'get', `/api/v1/manufacturing/job-cards/${cardId}/`, headers);
  expect(before.status).toBe('PLANNED');                                              // the office has not heard yet

  await context.setOffline(false);
  await expect(tablet.getByText(/taps are saved/)).toHaveCount(0, { timeout: 40_000 });
  const after = await api(page, 'get', `/api/v1/manufacturing/job-cards/${cardId}/`, headers);
  expect(after.status).toBe('IN_PROGRESS');
  await context.close();
  expect(problems, problems.join('\n')).toEqual([]);
  expect(tabletProblems.filter((p) => !/Network|net::|Failed to fetch/i.test(p)), tabletProblems.join('\n')).toEqual([]);
});
