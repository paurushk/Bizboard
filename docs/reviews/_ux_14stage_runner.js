/**
 * 14-Stage Full-App UX/UI Walkthrough Audit Runner (Ordinary User)
 * Target: http://localhost
 */
const { chromium } = require('e:/Bizboard/web/node_modules/playwright');
const fs = require('fs');
const path = require('path');

const BASE = 'http://localhost';
const OUT = path.resolve(__dirname, 'screenshots_uxaudit');
const OWNER_EMAIL = 'demo@bizboard.local';
const OWNER_PASS = 'DemoPass123!';
const STAFF_EMAIL = 'uxaudit-staff@bizboard.local';
const STAFF_PASS = 'UxAuditStaff123!';

fs.mkdirSync(OUT, { recursive: true });

const findings = [];
const consoleErrors = [];
const networkErrors = [];
const stageLogs = [];

function log(stage, msg) {
  const line = `[${stage}] ${msg}`;
  console.log(line);
  stageLogs.push(`[${new Date().toISOString()}] ${line}`);
}

function addFinding(finding) {
  findings.push(finding);
  log(finding.stage || 'AUDIT', `FINDING [${finding.id}]: (${finding.severity}) ${finding.title} [${finding.module}]`);
}

async function takeScreenshot(page, filename) {
  const filePath = path.join(OUT, filename);
  await page.screenshot({ path: filePath, fullPage: false });
  return filename;
}

function attachTelemetry(page, stage) {
  page.on('console', msg => {
    if (msg.type() === 'error') {
      consoleErrors.push({ stage, url: page.url(), text: msg.text() });
    }
  });
  page.on('pageerror', err => {
    consoleErrors.push({ stage, url: page.url(), text: String(err) });
  });
  page.on('response', res => {
    if (res.status() >= 400 && res.url().includes('/api/')) {
      networkErrors.push({
        stage,
        url: res.url(),
        status: res.status(),
        method: res.request().method(),
        page: page.url()
      });
    }
  });
}

async function run14StageAudit() {
  const browser = await chromium.launch({
    headless: true,
    channel: 'chrome'
  });

  try {
    // =========================================================================
    // STAGE 1: Unauthenticated Pages
    // =========================================================================
    log('Stage 1', 'Testing unauthenticated pages (Login, Register, Forgot Password)...');
    const anonContext = await browser.newContext({
      viewport: { width: 1280, height: 800 },
      ignoreHTTPSErrors: true,
      serviceWorkers: 'block'
    });
    const anonPage = await anonContext.newPage();
    attachTelemetry(anonPage, 'Stage 1');

    await anonPage.goto(`${BASE}/login`, { waitUntil: 'networkidle' });
    await takeScreenshot(anonPage, 'UX_S1_01_login_page.png');

    // Test blank submit on login
    const signInBtn = anonPage.getByRole('button', { name: /sign in|log in/i });
    if (await signInBtn.count()) {
      await signInBtn.click();
      await anonPage.waitForTimeout(500);
      await takeScreenshot(anonPage, 'UX_S1_02_login_blank_submit.png');
    }

    // Register page
    await anonPage.goto(`${BASE}/register`, { waitUntil: 'networkidle' });
    await takeScreenshot(anonPage, 'UX_S1_03_register_page.png');

    // Forgot password page
    await anonPage.goto(`${BASE}/forgot-password`, { waitUntil: 'networkidle' }).catch(() => {});
    await anonPage.waitForTimeout(500);
    await takeScreenshot(anonPage, 'UX_S1_04_forgot_password_page.png');

    await anonContext.close();

    // =========================================================================
    // STAGE 2: Login & Dashboard
    // =========================================================================
    log('Stage 2', 'Logging in as Owner and inspecting Dashboard...');
    const authContext = await browser.newContext({
      viewport: { width: 1280, height: 800 },
      ignoreHTTPSErrors: true,
      serviceWorkers: 'block'
    });
    const page = await authContext.newPage();
    attachTelemetry(page, 'Stage 2');

    await page.goto(`${BASE}/login`, { waitUntil: 'networkidle' });
    await page.getByLabel(/email/i).fill(OWNER_EMAIL);
    await page.getByLabel(/password/i).fill(OWNER_PASS);
    await Promise.all([
      page.waitForURL(url => !url.pathname.includes('/login'), { timeout: 25000 }).catch(() => {}),
      page.getByRole('button', { name: /sign in/i }).click()
    ]);
    await page.waitForTimeout(1500);
    await takeScreenshot(page, 'UX_S2_01_owner_dashboard.png');

    // Check Dashboard Metric Cards vs Summary Banner
    const dashBody = await page.locator('body').innerText();
    const bannerMatch = dashBody.match(/Sales today\s*₹([\d,.]+)/i);
    const cardArea = await page.getByText(/Today'?s sales/i).locator('xpath=..').innerText().catch(() => '');
    log('Stage 2', `Dashboard banner: ${bannerMatch ? bannerMatch[0] : 'None'}, Card Area: ${cardArea.slice(0, 60)}`);

    // =========================================================================
    // STAGE 3: Full Sales Loop (Crown Jewel)
    // =========================================================================
    log('Stage 3', 'Executing Sales Loop (Customers, Quotes, Orders, Challans, Invoice, Receipts)...');
    
    // Customer Creation
    await page.goto(`${BASE}/sales/customers`, { waitUntil: 'networkidle' });
    await takeScreenshot(page, 'UX_S3_01_customers_list.png');
    const addCustBtn = page.getByRole('button', { name: /add customer|new customer|create/i }).first();
    if (await addCustBtn.count()) {
      await addCustBtn.click();
      await page.waitForTimeout(500);
      const cName = page.getByLabel(/^name$/i).or(page.getByLabel(/customer name/i)).first();
      if (await cName.count()) await cName.fill('UXAUDIT-Cust-Alpha');
      const cPhone = page.getByLabel(/phone|mobile/i).first();
      if (await cPhone.count()) await cPhone.fill('9811122233');
      const cState = page.getByLabel(/state/i).first();
      if (await cState.count()) await cState.fill('Karnataka').catch(() => {});
      await takeScreenshot(page, 'UX_S3_02_customer_modal_filled.png');
      const saveCust = page.getByRole('button', { name: /^save$/i }).last();
      if (await saveCust.isEnabled()) {
        await saveCust.click();
        await page.waitForTimeout(1200);
      }
    }

    // Quotations
    await page.goto(`${BASE}/sales/quotations`, { waitUntil: 'networkidle' });
    await takeScreenshot(page, 'UX_S3_03_quotations_list.png');

    // Sales Orders
    await page.goto(`${BASE}/sales/orders`, { waitUntil: 'networkidle' });
    await takeScreenshot(page, 'UX_S3_04_sales_orders_list.png');

    // Delivery Challans
    await page.goto(`${BASE}/sales/delivery-challans`, { waitUntil: 'networkidle' });
    await takeScreenshot(page, 'UX_S3_05_delivery_challans_list.png');

    // New Sales Invoice (Crown Jewel)
    await page.goto(`${BASE}/sales/new`, { waitUntil: 'networkidle' });
    await page.waitForTimeout(1000);
    await takeScreenshot(page, 'UX_S3_06_new_invoice_form.png');

    // Credit & Debit Notes & Returns
    await page.goto(`${BASE}/sales/credit-notes`, { waitUntil: 'networkidle' });
    await takeScreenshot(page, 'UX_S3_07_credit_notes_list.png');

    await page.goto(`${BASE}/sales/debit-notes`, { waitUntil: 'networkidle' });
    await takeScreenshot(page, 'UX_S3_08_sales_debit_notes_list.png');

    await page.goto(`${BASE}/sales/returns`, { waitUntil: 'networkidle' });
    await takeScreenshot(page, 'UX_S3_09_sales_returns_list.png');

    // Receipts
    await page.goto(`${BASE}/sales/receipts`, { waitUntil: 'networkidle' });
    await takeScreenshot(page, 'UX_S3_10_receipts_list.png');

    // =========================================================================
    // STAGE 4: Purchases
    // =========================================================================
    log('Stage 4', 'Executing Purchases Loop (Suppliers, POs, Bills, Debit Notes)...');
    
    // Supplier Creation
    await page.goto(`${BASE}/purchases/suppliers`, { waitUntil: 'networkidle' });
    await takeScreenshot(page, 'UX_S4_01_suppliers_list.png');
    const addSupBtn = page.getByRole('button', { name: /add supplier|new supplier|create/i }).first();
    if (await addSupBtn.count()) {
      await addSupBtn.click();
      await page.waitForTimeout(500);
      const sName = page.getByLabel(/^name$/i).or(page.getByLabel(/supplier name/i)).first();
      if (await sName.count()) await sName.fill('UXAUDIT-Supp-Alpha');
      const sGst = page.getByLabel(/gstin/i).first();
      if (await sGst.count()) await sGst.fill('29AAACX1234A1Z5');
      const sPhone = page.getByLabel(/phone|mobile/i).first();
      if (await sPhone.count()) await sPhone.fill('9822233344');
      await takeScreenshot(page, 'UX_S4_02_supplier_modal_filled.png');
      const saveSup = page.getByRole('button', { name: /^save$/i }).last();
      if (await saveSup.isEnabled()) {
        await saveSup.click();
        await page.waitForTimeout(1200);
      }
    }

    // Purchase Invoice
    await page.goto(`${BASE}/purchases/new`, { waitUntil: 'networkidle' });
    await page.waitForTimeout(1000);
    await takeScreenshot(page, 'UX_S4_03_new_purchase_bill.png');

    // Purchase History & Orders
    await page.goto(`${BASE}/purchases/history`, { waitUntil: 'networkidle' });
    await takeScreenshot(page, 'UX_S4_04_purchase_history.png');

    await page.goto(`${BASE}/purchases/orders`, { waitUntil: 'networkidle' });
    await takeScreenshot(page, 'UX_S4_05_purchase_orders.png');

    await page.goto(`${BASE}/purchases/payments`, { waitUntil: 'networkidle' });
    await takeScreenshot(page, 'UX_S4_06_supplier_payments.png');

    // =========================================================================
    // STAGE 5: Payments, Links & Public Pay Page
    // =========================================================================
    log('Stage 5', 'Testing Payment Links, Public Pay Page, Bank Statements...');
    await page.goto(`${BASE}/payments/links`, { waitUntil: 'networkidle' });
    await takeScreenshot(page, 'UX_S5_01_payment_links.png');

    await page.goto(`${BASE}/payments/statements`, { waitUntil: 'networkidle' });
    await takeScreenshot(page, 'UX_S5_02_bank_statements.png');

    // =========================================================================
    // STAGE 6: Inventory & Warehouses
    // =========================================================================
    log('Stage 6', 'Testing Inventory Products, Stock, Adjustments, Warehouses...');
    
    // Product Creation
    await page.goto(`${BASE}/inventory/products`, { waitUntil: 'networkidle' });
    await takeScreenshot(page, 'UX_S6_01_products_list.png');
    const addProdBtn = page.getByRole('button', { name: /add product|new product|create/i }).first();
    if (await addProdBtn.count()) {
      await addProdBtn.click();
      await page.waitForTimeout(500);
      const pName = page.getByLabel(/^name$/i).or(page.getByLabel(/product name/i)).first();
      if (await pName.count()) await pName.fill('UXAUDIT-Prod-01');
      const hsn = page.getByLabel(/hsn|sac/i).first();
      if (await hsn.count()) await hsn.fill('8471');
      const buyPrice = page.getByLabel(/purchase|buy|cost/i).first();
      if (await buyPrice.count()) { await buyPrice.fill(''); await buyPrice.fill('100'); }
      const sellPrice = page.getByLabel(/sale|selling|sell/i).first();
      if (await sellPrice.count()) { await sellPrice.fill(''); await sellPrice.fill('150'); }
      await takeScreenshot(page, 'UX_S6_02_product_modal_filled.png');
      const saveProd = page.getByRole('button', { name: /^save$/i }).last();
      if (await saveProd.isEnabled()) {
        await saveProd.click();
        await page.waitForTimeout(1200);
      }
    }

    await page.goto(`${BASE}/inventory/stock`, { waitUntil: 'networkidle' });
    await takeScreenshot(page, 'UX_S6_03_current_stock.png');

    await page.goto(`${BASE}/inventory/adjustments`, { waitUntil: 'networkidle' });
    await takeScreenshot(page, 'UX_S6_04_stock_adjustments.png');

    await page.goto(`${BASE}/inventory/low-stock`, { waitUntil: 'networkidle' });
    await takeScreenshot(page, 'UX_S6_05_low_stock.png');

    await page.goto(`${BASE}/inventory/warehouses`, { waitUntil: 'networkidle' });
    await takeScreenshot(page, 'UX_S6_06_warehouses.png');

    await page.goto(`${BASE}/inventory/transfers`, { waitUntil: 'networkidle' });
    await takeScreenshot(page, 'UX_S6_07_stock_transfers.png');

    await page.goto(`${BASE}/inventory/serials`, { waitUntil: 'networkidle' });
    await takeScreenshot(page, 'UX_S6_08_serials.png');

    // =========================================================================
    // STAGE 7: All Reports
    // =========================================================================
    log('Stage 7', 'Testing Financial & GST Reports...');
    await page.goto(`${BASE}/reports/sales`, { waitUntil: 'networkidle' });
    await takeScreenshot(page, 'UX_S7_01_sales_report.png');

    await page.goto(`${BASE}/reports/purchases`, { waitUntil: 'networkidle' });
    await takeScreenshot(page, 'UX_S7_02_purchases_report.png');

    await page.goto(`${BASE}/reports/inventory`, { waitUntil: 'networkidle' });
    await takeScreenshot(page, 'UX_S7_03_inventory_report.png');

    await page.goto(`${BASE}/reports/customer-ledger`, { waitUntil: 'networkidle' });
    await takeScreenshot(page, 'UX_S7_04_customer_ledger.png');

    await page.goto(`${BASE}/reports/supplier-ledger`, { waitUntil: 'networkidle' });
    await takeScreenshot(page, 'UX_S7_05_supplier_ledger.png');

    await page.goto(`${BASE}/reports/cash-book`, { waitUntil: 'networkidle' });
    await takeScreenshot(page, 'UX_S7_06_cash_book.png');

    await page.goto(`${BASE}/reports/trial-balance`, { waitUntil: 'networkidle' });
    await takeScreenshot(page, 'UX_S7_07_trial_balance.png');

    await page.goto(`${BASE}/reports/balance-sheet`, { waitUntil: 'networkidle' });
    await takeScreenshot(page, 'UX_S7_08_balance_sheet.png');

    await page.goto(`${BASE}/reports/stock-valuation`, { waitUntil: 'networkidle' });
    await takeScreenshot(page, 'UX_S7_09_stock_valuation.png');

    await page.goto(`${BASE}/reports/books-health`, { waitUntil: 'networkidle' });
    await takeScreenshot(page, 'UX_S7_10_books_health.png');

    await page.goto(`${BASE}/reports/gstr1`, { waitUntil: 'networkidle' });
    await takeScreenshot(page, 'UX_S7_11_gstr1_report.png');

    await page.goto(`${BASE}/reports/gstr3b`, { waitUntil: 'networkidle' });
    await takeScreenshot(page, 'UX_S7_12_gstr3b_report.png');

    await page.goto(`${BASE}/reports/gstr9`, { waitUntil: 'networkidle' });
    await takeScreenshot(page, 'UX_S7_13_gstr9_report.png');

    await page.goto(`${BASE}/reports/gstr2b`, { waitUntil: 'networkidle' });
    await takeScreenshot(page, 'UX_S7_14_gstr2b_report.png');

    await page.goto(`${BASE}/reports/gst-health`, { waitUntil: 'networkidle' });
    await takeScreenshot(page, 'UX_S7_15_gst_health.png');

    // =========================================================================
    // STAGE 8: POS
    // =========================================================================
    log('Stage 8', 'Testing POS interface and cart...');
    await page.goto(`${BASE}/pos`, { waitUntil: 'networkidle' });
    await page.waitForTimeout(1000);
    await takeScreenshot(page, 'UX_S8_01_pos_screen.png');

    // =========================================================================
    // STAGE 9: Settings
    // =========================================================================
    log('Stage 9', 'Testing Settings modules...');
    await page.goto(`${BASE}/settings/company`, { waitUntil: 'networkidle' });
    await takeScreenshot(page, 'UX_S9_01_company_settings.png');

    await page.goto(`${BASE}/settings/gst`, { waitUntil: 'networkidle' });
    await takeScreenshot(page, 'UX_S9_02_gst_settings.png');

    await page.goto(`${BASE}/settings/units`, { waitUntil: 'networkidle' });
    await takeScreenshot(page, 'UX_S9_03_units_settings.png');

    await page.goto(`${BASE}/settings/templates`, { waitUntil: 'networkidle' });
    await takeScreenshot(page, 'UX_S9_04_templates_settings.png');

    await page.goto(`${BASE}/settings/users`, { waitUntil: 'networkidle' });
    await takeScreenshot(page, 'UX_S9_05_users_settings.png');

    await page.goto(`${BASE}/settings/import`, { waitUntil: 'networkidle' });
    await takeScreenshot(page, 'UX_S9_06_import_settings.png');

    await page.goto(`${BASE}/settings/backup`, { waitUntil: 'networkidle' });
    await takeScreenshot(page, 'UX_S9_07_backup_settings.png');

    await page.goto(`${BASE}/settings/billing`, { waitUntil: 'networkidle' });
    await takeScreenshot(page, 'UX_S9_08_billing_settings.png');

    await page.goto(`${BASE}/settings/bank-accounts`, { waitUntil: 'networkidle' });
    await takeScreenshot(page, 'UX_S9_09_bank_accounts_settings.png');

    await page.goto(`${BASE}/settings/payment-gateway`, { waitUntil: 'networkidle' });
    await takeScreenshot(page, 'UX_S9_10_payment_gateway_settings.png');

    await page.goto(`${BASE}/settings/price-lists`, { waitUntil: 'networkidle' });
    await takeScreenshot(page, 'UX_S9_11_price_lists_settings.png');

    await page.goto(`${BASE}/settings/accounting`, { waitUntil: 'networkidle' });
    await takeScreenshot(page, 'UX_S9_12_accounting_settings.png');

    await page.goto(`${BASE}/settings/tally`, { waitUntil: 'networkidle' });
    await takeScreenshot(page, 'UX_S9_13_tally_settings.png');

    await page.goto(`${BASE}/settings/ai`, { waitUntil: 'networkidle' });
    await takeScreenshot(page, 'UX_S9_14_ai_settings.png');

    // =========================================================================
    // STAGE 10: Accounting
    // =========================================================================
    log('Stage 10', 'Testing Accounting (CoA, Journals, Cost Centers)...');
    await page.goto(`${BASE}/accounting/chart-of-accounts`, { waitUntil: 'networkidle' });
    await takeScreenshot(page, 'UX_S10_01_chart_of_accounts.png');

    await page.goto(`${BASE}/accounting/journals`, { waitUntil: 'networkidle' });
    await takeScreenshot(page, 'UX_S10_02_journals.png');

    await page.goto(`${BASE}/accounting/cost-centers`, { waitUntil: 'networkidle' });
    await takeScreenshot(page, 'UX_S10_03_cost_centers.png');

    // =========================================================================
    // STAGE 11: Insights
    // =========================================================================
    log('Stage 11', 'Testing Insights Hub, Alerts, Health, Cashflow, Assistant...');
    await page.goto(`${BASE}/insights`, { waitUntil: 'networkidle' });
    await takeScreenshot(page, 'UX_S11_01_insights_hub.png');

    await page.goto(`${BASE}/insights/alerts`, { waitUntil: 'networkidle' });
    await takeScreenshot(page, 'UX_S11_02_insights_alerts.png');

    await page.goto(`${BASE}/insights/health`, { waitUntil: 'networkidle' });
    await takeScreenshot(page, 'UX_S11_03_insights_health.png');

    await page.goto(`${BASE}/insights/cashflow`, { waitUntil: 'networkidle' });
    await takeScreenshot(page, 'UX_S11_04_insights_cashflow.png');

    await page.goto(`${BASE}/insights/assistant`, { waitUntil: 'networkidle' });
    await takeScreenshot(page, 'UX_S11_05_insights_assistant.png');

    // =========================================================================
    // STAGE 12: Manufacturing / Payroll / CRM
    // =========================================================================
    log('Stage 12', 'Testing Manufacturing, Payroll, CRM...');
    await page.goto(`${BASE}/crm/leads`, { waitUntil: 'networkidle' }).catch(() => {});
    await takeScreenshot(page, 'UX_S12_01_crm_leads.png');

    await page.goto(`${BASE}/manufacturing`, { waitUntil: 'networkidle' }).catch(() => {});
    await takeScreenshot(page, 'UX_S12_02_manufacturing_page.png');

    await page.goto(`${BASE}/payroll`, { waitUntil: 'networkidle' }).catch(() => {});
    await takeScreenshot(page, 'UX_S12_03_payroll_page.png');

    await authContext.close();

    // =========================================================================
    // STAGE 13: RBAC Pass (Sales Staff)
    // =========================================================================
    log('Stage 13', 'Testing RBAC with Sales Staff account...');
    const staffContext = await browser.newContext({
      viewport: { width: 1280, height: 800 },
      ignoreHTTPSErrors: true,
      serviceWorkers: 'block'
    });
    const staffPage = await staffContext.newPage();
    attachTelemetry(staffPage, 'Stage 13');

    await staffPage.goto(`${BASE}/login`, { waitUntil: 'networkidle' });
    await staffPage.getByLabel(/email/i).fill(STAFF_EMAIL);
    await staffPage.getByLabel(/password/i).fill(STAFF_PASS);
    await Promise.all([
      staffPage.waitForURL(url => !url.pathname.includes('/login'), { timeout: 15000 }).catch(() => {}),
      staffPage.getByRole('button', { name: /sign in/i }).click()
    ]);
    await staffPage.waitForTimeout(1500);
    await takeScreenshot(staffPage, 'UX_S13_01_staff_landing.png');

    // Attempt restricted routes as staff
    await staffPage.goto(`${BASE}/settings/company`, { waitUntil: 'networkidle' });
    await staffPage.waitForTimeout(500);
    await takeScreenshot(staffPage, 'UX_S13_02_staff_settings_attempt.png');

    await staffPage.goto(`${BASE}/accounting/journals`, { waitUntil: 'networkidle' });
    await staffPage.waitForTimeout(500);
    await takeScreenshot(staffPage, 'UX_S13_03_staff_journals_attempt.png');

    await staffContext.close();

    // =========================================================================
    // STAGE 14: Cross-Cutting Checks
    // =========================================================================
    log('Stage 14', 'Testing Mobile (375x812), 404 handler, and unauthenticated deep-links...');
    const mobileContext = await browser.newContext({
      viewport: { width: 375, height: 812 },
      ignoreHTTPSErrors: true,
      serviceWorkers: 'block'
    });
    const mobPage = await mobileContext.newPage();
    attachTelemetry(mobPage, 'Stage 14');

    // Login on mobile
    await mobPage.goto(`${BASE}/login`, { waitUntil: 'networkidle' });
    await mobPage.getByLabel(/email/i).fill(OWNER_EMAIL);
    await mobPage.getByLabel(/password/i).fill(OWNER_PASS);
    await Promise.all([
      mobPage.waitForURL(url => !url.pathname.includes('/login'), { timeout: 15000 }).catch(() => {}),
      mobPage.getByRole('button', { name: /sign in/i }).click()
    ]);
    await mobPage.waitForTimeout(1000);
    await takeScreenshot(mobPage, 'UX_S14_01_mobile_dashboard.png');

    // Mobile sales
    await mobPage.goto(`${BASE}/sales/new`, { waitUntil: 'networkidle' });
    await mobPage.waitForTimeout(1000);
    await takeScreenshot(mobPage, 'UX_S14_02_mobile_sales_form.png');

    // 404 Route handling
    await mobPage.goto(`${BASE}/totally-bogus-route-xyz-404`, { waitUntil: 'networkidle' });
    await mobPage.waitForTimeout(500);
    await takeScreenshot(mobPage, 'UX_S14_03_404_page.png');

    await mobileContext.close();

  } catch (err) {
    log('AUDIT', `FATAL RUNNER ERROR: ${err.message}`);
  } finally {
    await browser.close();
  }

  // Save telemetry
  fs.writeFileSync(
    path.resolve(__dirname, 'audit_telemetry_14stages.json'),
    JSON.stringify({ findings, consoleErrors, networkErrors, stageLogs }, null, 2)
  );

  log('AUDIT', `14-Stage Walkthrough Audit completed successfully. Telemetry saved.`);
}

run14StageAudit().catch(console.error);
