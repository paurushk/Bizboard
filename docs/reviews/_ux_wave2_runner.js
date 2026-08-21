/**
 * UX Wave 2 audit runner — local Playwright against http://localhost
 * Creates UXWAVE2-* entities, captures screenshots, logs telemetry.
 */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const BASE = 'http://localhost';
const OUT = path.resolve(__dirname, '../../docs/reviews/screenshots_wave2');
const FINDINGS = path.resolve(__dirname, '../../docs/reviews/UX_AUDIT_WAVE2_FINDINGS.md');
const EMAIL = 'demo@bizboard.local';
const PASS = 'DemoPass123!';

fs.mkdirSync(OUT, { recursive: true });

const issues = [];
const notes = [];

function issue(partial) {
  const id = `UXW2-${String(issues.length + 1).padStart(3, '0')}`;
  issues.push({ id, ...partial });
  return id;
}

async function shot(page, name) {
  const file = path.join(OUT, name);
  await page.screenshot({ path: file, fullPage: false });
  return name;
}

async function login(page) {
  await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded', timeout: 60000 });
  // Bypass stuck offline SW page if present
  if (await page.getByRole('heading', { name: /offline/i }).count()) {
    await page.getByRole('link', { name: /try again/i }).click().catch(() => {});
    await page.goto(`${BASE}/login?bypass=${Date.now()}`, { waitUntil: 'networkidle', timeout: 60000 });
  }
  await page.getByLabel(/email/i).fill(EMAIL);
  await page.getByLabel(/password/i).fill(PASS);
  await Promise.all([
    page.waitForURL((u) => !u.pathname.includes('/login'), { timeout: 30000 }).catch(() => {}),
    page.getByRole('button', { name: /sign in/i }).click(),
  ]);
  await page.waitForTimeout(1500);
  if (page.url().includes('/login')) {
    throw new Error('Login failed — still on /login');
  }
}

async function collectConsole(page) {
  const errors = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error') errors.push(msg.text());
  });
  page.on('pageerror', (err) => errors.push(String(err)));
  page.on('response', (res) => {
    if (res.status() >= 400 && res.url().includes('/api/')) {
      errors.push(`HTTP ${res.status()} ${res.request().method()} ${res.url()}`);
    }
  });
  return errors;
}

async function openNav(page, section, linkName) {
  // Desktop: section is a button; Mobile: hamburger first
  const hamburger = page.getByRole('button', { name: /open navigation|menu/i });
  if (await hamburger.isVisible().catch(() => false)) {
    await hamburger.click();
    await page.waitForTimeout(300);
  }
  const sectionBtn = page.getByRole('button', { name: section, exact: true });
  if (await sectionBtn.count()) {
    const expanded = await sectionBtn.getAttribute('aria-expanded');
    if (expanded !== 'true') await sectionBtn.click();
  }
  await page.getByRole('link', { name: linkName, exact: true }).first().click();
  await page.waitForTimeout(800);
}

async function main() {
  const browser = await chromium.launch({
    headless: true,
    channel: 'chrome', // use system Chrome when Playwright browser download fails
  });
  const context = await browser.newContext({
    viewport: { width: 1280, height: 800 },
    ignoreHTTPSErrors: true,
    serviceWorkers: 'block', // avoid false offline shell
  });
  const page = await context.newPage();
  const telemetry = await collectConsole(page);

  notes.push(`Workers note: celery beat/worker may be unhealthy (checked via docker earlier).`);

  // --- Phase 1 login ---
  await login(page);
  await shot(page, 'UXW2-P1_dashboard_desktop.png');

  // Dashboard inconsistency check
  const body = await page.locator('#main-content').innerText().catch(() => page.locator('body').innerText());
  const bannerMatch = body.match(/Sales today\s*₹([\d,.]+)/i);
  const cardToday = await page.getByText(/Today'?s sales/i).locator('xpath=..').innerText().catch(() => '');
  notes.push(`Dashboard banner snippet: ${bannerMatch ? bannerMatch[0] : 'n/a'}; card area: ${cardToday.slice(0, 120)}`);

  // --- Company / GST ---
  await page.goto(`${BASE}/settings/company`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(1000);
  await shot(page, 'UXW2-P2_company_settings.png');
  const companyText = await page.locator('body').innerText();
  if (!/GSTIN|gstin/i.test(companyText)) {
    issue({
      title: 'Company settings page has no GSTIN or currency fields',
      module: '/settings/company',
      type: 'Usability',
      severity: 'Medium',
      steps: ['Go to Settings → Company', 'Look for GSTIN / currency'],
      expected: 'GSTIN and currency visible on company profile for Indian GST businesses',
      actual: 'Only trade name, address, bank/UPI fields; GSTIN lives elsewhere (Settings → GST)',
      impact: 'First-time users may think GST is not configured',
      evidence: 'UXW2-P2_company_settings.png',
      fix: 'Surface GSTIN summary + link to GST settings on Company page, or merge key tax identity fields',
    });
  }

  await page.goto(`${BASE}/settings/gst`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(1000);
  await shot(page, 'UXW2-P2_gst_settings.png');

  // Invalid GSTIN probe on GST page if editable
  const gstinField = page.getByLabel(/gstin/i).first();
  if (await gstinField.count()) {
    const original = await gstinField.inputValue().catch(() => '');
    await gstinField.fill('INVALID');
    await page.getByRole('button', { name: /save/i }).click().catch(() => {});
    await page.waitForTimeout(800);
    await shot(page, 'UXW2-P2_gst_invalid_attempt.png');
    const after = await page.locator('body').innerText();
    if (!/invalid|format|checksum|must be/i.test(after) && original) {
      // restore
      await gstinField.fill(original);
    }
  }

  // --- Suppliers ---
  await page.goto(`${BASE}/purchases/suppliers`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(1000);
  await shot(page, 'UXW2-P2_suppliers_list.png');

  const addSupplier =
    page.getByRole('button', { name: /add supplier|new supplier|create/i }).first();
  if (await addSupplier.count()) {
    await addSupplier.click();
    await page.waitForTimeout(500);
    await shot(page, 'UXW2-P2_supplier_modal.png');

    // Empty save / disabled
    const saveBtn = page.getByRole('button', { name: /^save$/i }).last();
    const disabled = await saveBtn.isDisabled().catch(() => false);
    notes.push(`Supplier Save disabled when empty: ${disabled}`);

    // Invalid GSTIN
    const nameField = page.getByLabel(/^name$/i).or(page.getByLabel(/supplier name/i)).first();
    if (await nameField.count()) await nameField.fill('UXWAVE2-Supplier-Alpha');
    const gstField = page.getByLabel(/gstin/i).first();
    if (await gstField.count()) {
      await gstField.fill('29AAAAA0000A1Z');
      await page.waitForTimeout(400);
      await shot(page, 'UXW2-P2_supplier_invalid_gstin.png');
      const modalText = await page.locator('body').innerText();
      if (!/invalid|checksum|format|15/i.test(modalText)) {
        issue({
          title: 'Invalid GSTIN accepted or no clear inline validation on supplier form',
          module: '/purchases/suppliers',
          type: 'Usability',
          severity: 'Medium',
          steps: ['Open Add Supplier', 'Enter truncated/invalid GSTIN', 'Observe feedback'],
          expected: 'Clear inline error explaining GSTIN format',
          actual: 'No obvious invalid-GSTIN message observed before save',
          impact: 'Bad GSTINs enter masters and break e-invoice / GSTR later',
          evidence: 'UXW2-P2_supplier_invalid_gstin.png',
          fix: 'Validate GSTIN length/checksum on blur with Hindi/English helper text',
        });
      }
      // Valid Karnataka GSTIN pattern for same-state CGST/SGST testing
      await gstField.fill('29AAACX1234A1Z5');
    }

    // Fill address-ish fields if present
    for (const [label, val] of [
      [/phone|mobile/i, '9876543210'],
      [/email/i, 'uxwave2-supplier@example.com'],
      [/address/i, 'UXWAVE2 Street 1'],
      [/city/i, 'Bengaluru'],
      [/state/i, 'Karnataka'],
      [/pin|pincode|postal/i, '560001'],
    ]) {
      const f = page.getByLabel(label).first();
      if (await f.count()) await f.fill(val).catch(() => {});
    }

    await shot(page, 'UXW2-P2_supplier_filled.png');
    if (await saveBtn.isEnabled()) {
      await saveBtn.click();
      await page.waitForTimeout(1500);
    }
    await shot(page, 'UXW2-P2_supplier_after_save.png');
  } else {
    issue({
      title: 'Cannot find Add Supplier control',
      module: '/purchases/suppliers',
      type: 'Broken Flow',
      severity: 'High',
      steps: ['Go to Purchases → Suppliers'],
      expected: 'Visible Add/New Supplier button',
      actual: 'No matching button found',
      impact: 'Blocks purchase chain',
      evidence: 'UXW2-P2_suppliers_list.png',
      fix: 'Ensure primary CTA is visible',
    });
  }

  // --- Products ---
  await page.goto(`${BASE}/inventory/products`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(1000);
  await shot(page, 'UXW2-P2_products_list.png');
  const addProduct = page.getByRole('button', { name: /add product|new product|create/i }).first();
  if (await addProduct.count()) {
    await addProduct.click();
    await page.waitForTimeout(500);
    const pname = page.getByLabel(/^name$/i).or(page.getByLabel(/product name/i)).first();
    if (await pname.count()) await pname.fill('UXWAVE2-Item-Widget');
    for (const [label, val] of [
      [/hsn|sac/i, '8471'],
      [/sale|selling|sell/i, '150'],
      [/purchase|buy|cost/i, '100'],
      [/gst|tax rate|rate/i, '18'],
      [/opening|stock/i, '10'],
    ]) {
      const f = page.getByLabel(label).first();
      if (await f.count()) {
        await f.fill('').catch(() => {});
        await f.fill(String(val)).catch(() => {});
      }
    }
    // Also try placeholder-based
    const inputs = page.locator('[role="dialog"] input, .MuiDialog-root input, form input');
    const count = await inputs.count();
    notes.push(`Product modal input count: ${count}`);
    await shot(page, 'UXW2-P2_product_filled.png');
    const pSave = page.getByRole('button', { name: /^save$/i }).last();
    if (await pSave.isEnabled().catch(() => false)) {
      await pSave.click();
      await page.waitForTimeout(1500);
    } else {
      // Try Create
      await page.getByRole('button', { name: /create|add/i }).last().click().catch(() => {});
      await page.waitForTimeout(1500);
    }
    await shot(page, 'UXW2-P2_product_after_save.png');
  }

  // Stock before purchase
  await page.goto(`${BASE}/inventory/stock`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(1000);
  await shot(page, 'UXW2-P2_stock_before_purchase.png');
  const stockBefore = await page.locator('body').innerText();
  notes.push(`Stock page contains Widget: ${/UXWAVE2-Item-Widget/i.test(stockBefore)}`);

  // --- Purchase invoice ---
  await page.goto(`${BASE}/purchases/new`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(1200);
  await shot(page, 'UXW2-P2_purchase_new.png');

  // Try select supplier combobox
  const supplierCombo = page.getByRole('combobox', { name: /supplier/i }).or(page.getByLabel(/supplier/i)).first();
  if (await supplierCombo.count()) {
    await supplierCombo.click();
    await page.waitForTimeout(400);
    await page.keyboard.type('UXWAVE2-Supplier-Alpha');
    await page.waitForTimeout(600);
    await page.keyboard.press('Enter').catch(() => {});
    await page.getByRole('option', { name: /UXWAVE2-Supplier-Alpha/i }).first().click().catch(() => {});
  }

  // Line item product
  const productCombo = page.getByRole('combobox', { name: /product|item/i }).first();
  if (await productCombo.count()) {
    await productCombo.click();
    await page.keyboard.type('UXWAVE2-Item-Widget');
    await page.waitForTimeout(600);
    await page.getByRole('option', { name: /UXWAVE2-Item-Widget/i }).first().click().catch(() => {});
  }

  // Quantity 20
  const qty = page.getByLabel(/qty|quantity/i).first();
  if (await qty.count()) {
    await qty.fill('20');
  } else {
    // fallback: spinbuttons / numbered inputs in grid
    const spin = page.locator('input[type="number"]').first();
    if (await spin.count()) await spin.fill('20');
  }

  await page.waitForTimeout(800);
  await shot(page, 'UXW2-P2_purchase_filled.png');
  const purchaseText = await page.locator('body').innerText();
  notes.push(`Purchase tax snippet: ${purchaseText.match(/CGST|SGST|IGST|Tax|Total[^\n]{0,40}/gi)?.slice(0, 8)?.join(' | ') || 'n/a'}`);

  const savePurchase = page.getByRole('button', { name: /save|create|post|confirm/i }).first();
  if (await savePurchase.count()) {
    await savePurchase.click();
    await page.waitForTimeout(2000);
  }
  await shot(page, 'UXW2-P2_purchase_after_save.png');

  await page.goto(`${BASE}/inventory/stock`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(1000);
  await shot(page, 'UXW2-P2_stock_after_purchase.png');

  // --- Customer ---
  await page.goto(`${BASE}/sales/customers`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(800);
  const addCust = page.getByRole('button', { name: /add customer|new customer|create/i }).first();
  if (await addCust.count()) {
    await addCust.click();
    await page.waitForTimeout(400);
    const cname = page.getByLabel(/^name$/i).or(page.getByLabel(/customer name/i)).first();
    if (await cname.count()) await cname.fill('UXWAVE2-Customer-Beta');
    const cstate = page.getByLabel(/state/i).first();
    if (await cstate.count()) await cstate.fill('Karnataka');
    const cSave = page.getByRole('button', { name: /^save$/i }).last();
    if (await cSave.isEnabled().catch(() => false)) await cSave.click();
    await page.waitForTimeout(1200);
    await shot(page, 'UXW2-P2_customer_created.png');
  }

  // --- Sales invoice ---
  await page.goto(`${BASE}/sales/new`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(1200);
  await shot(page, 'UXW2-P2_sales_new.png');
  const custCombo = page.getByRole('combobox', { name: /customer/i }).or(page.getByLabel(/customer/i)).first();
  if (await custCombo.count()) {
    await custCombo.click();
    await page.keyboard.type('UXWAVE2-Customer-Beta');
    await page.waitForTimeout(600);
    await page.getByRole('option', { name: /UXWAVE2-Customer-Beta/i }).first().click().catch(() => {});
  }
  const sProd = page.getByRole('combobox', { name: /product|item/i }).first();
  if (await sProd.count()) {
    await sProd.click();
    await page.keyboard.type('UXWAVE2-Item-Widget');
    await page.waitForTimeout(600);
    await page.getByRole('option', { name: /UXWAVE2-Item-Widget/i }).first().click().catch(() => {});
  }
  const sqty = page.getByLabel(/qty|quantity/i).first();
  if (await sqty.count()) await sqty.fill('5');
  else {
    const spin = page.locator('input[type="number"]').first();
    if (await spin.count()) await spin.fill('5');
  }
  await page.waitForTimeout(800);
  await shot(page, 'UXW2-P2_sales_filled.png');
  const salesText = await page.locator('body').innerText();
  notes.push(`Sales tax snippet: ${salesText.match(/CGST|SGST|IGST|Tax|Total[^\n]{0,40}/gi)?.slice(0, 8)?.join(' | ') || 'n/a'}`);
  const saveSales = page.getByRole('button', { name: /save|create|post|confirm/i }).first();
  if (await saveSales.count()) {
    await saveSales.click();
    await page.waitForTimeout(2000);
  }
  await shot(page, 'UXW2-P2_sales_after_save.png');

  await page.goto(`${BASE}/inventory/stock`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(1000);
  await shot(page, 'UXW2-P2_stock_after_sales.png');

  // --- Reports sweep ---
  for (const [route, name] of [
    ['/reports/sales', 'sales_register'],
    ['/reports/purchases', 'purchase_register'],
    ['/reports/inventory', 'stock_summary'],
    ['/reports/customer-ledger', 'customer_ledger'],
    ['/reports/supplier-ledger', 'supplier_ledger'],
    ['/reports/cash-book', 'cash_book_daybook'],
    ['/reports/gstr1', 'gstr1'],
    ['/reports/gstr3b', 'gstr3b'],
    ['/reports/profit-and-loss', 'pnl'],
    ['/reports/balance-sheet', 'balance_sheet'],
    ['/reports/trial-balance', 'trial_balance'],
  ]) {
    await page.goto(`${BASE}${route}`, { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(1200);
    await shot(page, `UXW2-P2_report_${name}.png`);
    const t = await page.locator('body').innerText();
    if (/error|failed|something went wrong|traceback/i.test(t)) {
      issue({
        title: `Report page error: ${name}`,
        module: route,
        type: 'Functional',
        severity: 'High',
        steps: [`Open ${route}`],
        expected: 'Report loads with data or empty state',
        actual: `Error-like content on page. Telemetry: ${telemetry.slice(-3).join('; ')}`,
        impact: 'Accountant cannot verify books',
        evidence: `UXW2-P2_report_${name}.png`,
        fix: 'Fix API/report rendering failure',
      });
    }
  }

  // --- Mobile viewport quick pass ---
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto(`${BASE}/`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(1000);
  await shot(page, 'UXW2-P3_mobile_dashboard.png');
  await page.goto(`${BASE}/sales/history`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(1000);
  await shot(page, 'UXW2-P3_mobile_sales_history.png');
  const mobileSales = await page.locator('body').innerText();
  // Check horizontal overflow heuristically via scrollWidth
  const overflow = await page.evaluate(() => {
    const el = document.querySelector('table, .MuiTable-root, [role="table"]');
    if (!el) return null;
    return { scrollWidth: el.scrollWidth, clientWidth: el.clientWidth };
  });
  if (overflow && overflow.scrollWidth > overflow.clientWidth + 8) {
    issue({
      title: 'Sales history table overflows horizontally on mobile',
      module: '/sales/history (375x812)',
      type: 'Visual / UI',
      severity: 'Medium',
      steps: ['Set viewport 375x812', 'Open Sales history'],
      expected: 'Readable table or card list without forcing awkward horizontal scroll of whole page',
      actual: `Table scrollWidth=${overflow.scrollWidth} clientWidth=${overflow.clientWidth}`,
      impact: 'Hard to use on phone for shopkeepers',
      evidence: 'UXW2-P3_mobile_sales_history.png',
      fix: 'Use stacked cards or sticky first column on narrow viewports',
    });
  }

  // Edge: empty sales save double-click probe
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto(`${BASE}/sales/new`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(800);
  const save2 = page.getByRole('button', { name: /save|create|post/i }).first();
  if (await save2.count()) {
    await save2.dblclick().catch(async () => {
      await save2.click();
      await save2.click();
    });
    await page.waitForTimeout(1000);
    await shot(page, 'UXW2-P3_sales_empty_double_save.png');
  }

  // Write findings append
  let md = `\n## Automated runner notes\n\n`;
  for (const n of notes) md += `- ${n}\n`;
  md += `\n### Telemetry (sample)\n\`\`\`\n${telemetry.slice(0, 40).join('\n')}\n\`\`\`\n`;
  md += `\n## Issues discovered (runner + interactive)\n\n`;
  for (const i of issues) {
    md += `### [${i.id}] ${i.title}\n`;
    md += `- **Module / Route**: \`${i.module}\`\n`;
    md += `- **Issue Type**: \`${i.type}\`\n`;
    md += `- **Severity**: \`${i.severity}\`\n`;
    md += `- **Steps to Reproduce**:\n`;
    (i.steps || []).forEach((s, idx) => {
      md += `  ${idx + 1}. ${s}\n`;
    });
    md += `- **Expected Behaviour**: ${i.expected}\n`;
    md += `- **Actual Behaviour**: ${i.actual}\n`;
    md += `- **Impact**: ${i.impact}\n`;
    md += `- **Evidence / Screenshot**: \`![Evidence](screenshots_wave2/${i.evidence})\`\n`;
    md += `- **Suggested Fix**: ${i.fix}\n\n`;
  }

  fs.appendFileSync(FINDINGS, md);
  fs.writeFileSync(path.join(OUT, '_wave2_runner_meta.json'), JSON.stringify({ notes, issues, telemetry: telemetry.slice(0, 100) }, null, 2));

  console.log(JSON.stringify({ ok: true, issues: issues.length, notes: notes.length, telemetry: telemetry.length }, null, 2));
  await browser.close();
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
