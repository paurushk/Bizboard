/**
 * Full End-to-End UX & Functional Walkthrough Audit Runner (Wave 2)
 * Runs against http://localhost
 */
const { chromium } = require('e:/Bizboard/web/node_modules/playwright');
const fs = require('fs');
const path = require('path');

const BASE = 'http://localhost';
const OUT = path.resolve(__dirname, 'screenshots_wave2');
const EMAIL = 'demo@bizboard.local';
const PASS = 'DemoPass123!';

fs.mkdirSync(OUT, { recursive: true });

const findings = [];
const consoleErrors = [];
const networkErrors = [];
const auditLog = [];

function log(msg) {
  console.log(`[AUDIT] ${msg}`);
  auditLog.push(`[${new Date().toISOString()}] ${msg}`);
}

function addFinding(f) {
  const id = `UXW2-${String(findings.length + 1).padStart(3, '0')}`;
  const finding = { id, ...f };
  findings.push(finding);
  log(`FINDING [${id}]: (${f.severity}) ${f.title} [${f.module}]`);
  return id;
}

async function takeScreenshot(page, filename) {
  const filePath = path.join(OUT, filename);
  await page.screenshot({ path: filePath, fullPage: false });
  return filename;
}

async function login(page) {
  log('Navigating to login page...');
  await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded', timeout: 30000 });
  await page.waitForTimeout(1000);

  // Check if stuck on offline SW page
  if (await page.getByRole('heading', { name: /offline/i }).count()) {
    log('Offline page detected on login, clicking Try Again / reloading');
    await page.getByRole('link', { name: /try again/i }).click().catch(() => {});
    await page.goto(`${BASE}/login?bypass=${Date.now()}`, { waitUntil: 'networkidle', timeout: 30000 });
  }

  await page.getByLabel(/email/i).fill(EMAIL);
  await page.getByLabel(/password/i).fill(PASS);
  
  await Promise.all([
    page.waitForURL(url => !url.pathname.includes('/login'), { timeout: 20000 }).catch(() => {}),
    page.getByRole('button', { name: /sign in/i }).click()
  ]);
  await page.waitForTimeout(1500);

  if (page.url().includes('/login')) {
    throw new Error('Login failed — still on /login');
  }
  log(`Login successful, currently at: ${page.url()}`);
}

function attachTelemetry(page) {
  page.on('console', msg => {
    if (msg.type() === 'error') {
      consoleErrors.push({ url: page.url(), text: msg.text() });
    }
  });
  page.on('pageerror', err => {
    consoleErrors.push({ url: page.url(), text: String(err) });
  });
  page.on('response', res => {
    if (res.status() >= 400 && res.url().includes('/api/')) {
      networkErrors.push({
        url: res.url(),
        status: res.status(),
        method: res.request().method(),
        page: page.url()
      });
    }
  });
}

async function runAudit() {
  const browser = await chromium.launch({
    headless: true,
    channel: 'chrome'
  });

  const context = await browser.newContext({
    viewport: { width: 1280, height: 800 },
    ignoreHTTPSErrors: true,
    serviceWorkers: 'block' // prevent offline service worker caching issues
  });

  const page = await context.newPage();
  attachTelemetry(page);

  log('Starting Wave 2 Full App Audit...');

  try {
    // ----------------------------------------------------
    // Phase 0: Pre-Flight & Login
    // ----------------------------------------------------
    await login(page);
    await takeScreenshot(page, 'UXW2_001_dashboard_desktop.png');

    // Check Dashboard metrics mismatch
    const dashText = await page.locator('body').innerText();
    const bannerMatch = dashText.match(/Sales today\s*₹([\d,.]+)/i);
    const cardArea = await page.getByText(/Today'?s sales/i).locator('xpath=..').innerText().catch(() => '');
    log(`Dashboard banner match: ${bannerMatch ? bannerMatch[0] : 'None'}, Card Area: ${cardArea.slice(0, 80)}`);

    if (bannerMatch && cardArea && !cardArea.includes(bannerMatch[1])) {
      addFinding({
        title: 'Dashboard summary banner contradicts KPI metric cards',
        module: '/',
        type: 'Data Integrity',
        severity: 'Critical',
        viewport: 'Desktop & Mobile',
        steps: [
          'Log in as demo@bizboard.local',
          'Inspect Today\'s Business Summary banner at top of dashboard',
          'Compare sales/AR/AP figures with the KPI metric cards below'
        ],
        expected: 'Banner summary and KPI cards must present reconciled, consistent figures for today/MTD',
        actual: `Banner displays "${bannerMatch[0]}" while KPI card shows conflicting values (${cardArea.trim()})`,
        impact: 'Business owners cannot trust financial figures on the home dashboard at a glance',
        fix: 'Use a single synchronized data source / API endpoint for dashboard summary metrics',
        evidence: 'UXW2_001_dashboard_desktop.png'
      });
    }

    // ----------------------------------------------------
    // Phase 1: Core Value Chain (Supplier -> Purchase -> Customer -> Sale -> Stock)
    // ----------------------------------------------------
    log('Phase 1: Testing Company & GST Settings...');
    await page.goto(`${BASE}/settings/company`, { waitUntil: 'networkidle' });
    await takeScreenshot(page, 'UXW2_002_company_settings.png');

    await page.goto(`${BASE}/settings/gst`, { waitUntil: 'networkidle' });
    await takeScreenshot(page, 'UXW2_003_gst_settings.png');

    // Supplier Creation
    log('Creating Supplier UXW2-Supplier-Alpha...');
    await page.goto(`${BASE}/purchases/suppliers`, { waitUntil: 'networkidle' });
    await takeScreenshot(page, 'UXW2_004_suppliers_list.png');
    
    const addSupBtn = page.getByRole('button', { name: /add supplier|new supplier|create/i }).first();
    if (await addSupBtn.count()) {
      await addSupBtn.click();
      await page.waitForTimeout(500);
      
      const nameInput = page.getByLabel(/^name$/i).or(page.getByLabel(/supplier name/i)).first();
      if (await nameInput.count()) await nameInput.fill('UXW2-Supplier-Alpha');
      
      const gstInput = page.getByLabel(/gstin/i).first();
      if (await gstInput.count()) await gstInput.fill('29AAACX1234A1Z5');
      
      const phoneInput = page.getByLabel(/phone|mobile/i).first();
      if (await phoneInput.count()) await phoneInput.fill('9876543210');
      
      const stateInput = page.getByLabel(/state/i).first();
      if (await stateInput.count()) await stateInput.fill('Karnataka').catch(() => {});

      await takeScreenshot(page, 'UXW2_005_supplier_form_filled.png');
      const saveSup = page.getByRole('button', { name: /^save$/i }).last();
      if (await saveSup.isEnabled()) {
        await saveSup.click();
        await page.waitForTimeout(1200);
      }
    }

    // Product Creation
    log('Creating Product UXW2-Item-Widget...');
    await page.goto(`${BASE}/inventory/products`, { waitUntil: 'networkidle' });
    await takeScreenshot(page, 'UXW2_006_products_list.png');
    
    const addProdBtn = page.getByRole('button', { name: /add product|new product|create/i }).first();
    if (await addProdBtn.count()) {
      await addProdBtn.click();
      await page.waitForTimeout(500);
      
      const pName = page.getByLabel(/^name$/i).or(page.getByLabel(/product name/i)).first();
      if (await pName.count()) await pName.fill('UXW2-Item-Widget');

      const hsn = page.getByLabel(/hsn|sac/i).first();
      if (await hsn.count()) await hsn.fill('8471');

      const buyPrice = page.getByLabel(/purchase|buy|cost/i).first();
      if (await buyPrice.count()) { await buyPrice.fill(''); await buyPrice.fill('100'); }

      const sellPrice = page.getByLabel(/sale|selling|sell/i).first();
      if (await sellPrice.count()) { await sellPrice.fill(''); await sellPrice.fill('150'); }

      await takeScreenshot(page, 'UXW2_007_product_modal_filled.png');
      const saveProd = page.getByRole('button', { name: /^save$/i }).last();
      if (await saveProd.isEnabled()) {
        await saveProd.click();
        await page.waitForTimeout(1200);
      }
    }

    // Purchase Invoice
    log('Opening Purchase Bill page...');
    await page.goto(`${BASE}/purchases/new`, { waitUntil: 'networkidle' });
    await page.waitForTimeout(1000);
    await takeScreenshot(page, 'UXW2_008_new_purchase_page.png');

    // Customer Creation
    log('Creating Customer UXW2-Customer-Beta...');
    await page.goto(`${BASE}/sales/customers`, { waitUntil: 'networkidle' });
    await takeScreenshot(page, 'UXW2_009_customers_list.png');
    const addCustBtn = page.getByRole('button', { name: /add customer|new customer|create/i }).first();
    if (await addCustBtn.count()) {
      await addCustBtn.click();
      await page.waitForTimeout(500);

      const cName = page.getByLabel(/^name$/i).or(page.getByLabel(/customer name/i)).first();
      if (await cName.count()) await cName.fill('UXW2-Customer-Beta');

      const cPhone = page.getByLabel(/phone|mobile/i).first();
      if (await cPhone.count()) await cPhone.fill('9123456789');

      const cState = page.getByLabel(/state/i).first();
      if (await cState.count()) await cState.fill('Karnataka').catch(() => {});

      await takeScreenshot(page, 'UXW2_010_customer_form_filled.png');
      const saveCust = page.getByRole('button', { name: /^save$/i }).last();
      if (await saveCust.isEnabled()) {
        await saveCust.click();
        await page.waitForTimeout(1200);
      }
    }

    // Sales Invoice Creation
    log('Opening Sales Invoice page...');
    await page.goto(`${BASE}/sales/new`, { waitUntil: 'networkidle' });
    await page.waitForTimeout(1000);
    await takeScreenshot(page, 'UXW2_011_new_sales_page.png');

    // ----------------------------------------------------
    // Phase 2: Full Sales & Purchases Module Sweep
    // ----------------------------------------------------
    const routesToSweep = [
      // Sales Loop
      { url: '/sales/history', name: 'sales_history', title: 'Sales History' },
      { url: '/sales/quotations', name: 'quotations', title: 'Quotations' },
      { url: '/sales/orders', name: 'sales_orders', title: 'Sales Orders' },
      { url: '/sales/orders/new', name: 'new_sales_order', title: 'New Sales Order' },
      { url: '/sales/delivery-challans', name: 'delivery_challans', title: 'Delivery Challans' },
      { url: '/sales/delivery-challans/new', name: 'new_delivery_challan', title: 'New Delivery Challan' },
      { url: '/sales/credit-notes', name: 'credit_notes', title: 'Credit Notes' },
      { url: '/sales/credit-notes/new', name: 'new_credit_note', title: 'New Credit Note' },
      { url: '/sales/debit-notes', name: 'sales_debit_notes', title: 'Sales Debit Notes' },
      { url: '/sales/returns', name: 'sales_returns', title: 'Sales Returns' },
      { url: '/sales/receipts', name: 'sales_receipts', title: 'Receipts' },
      { url: '/sales/upload', name: 'sales_bill_upload', title: 'Sales Bill Upload' },

      // Purchases Loop
      { url: '/purchases/history', name: 'purchase_history', title: 'Purchase History' },
      { url: '/purchases/orders', name: 'purchase_orders', title: 'Purchase Orders' },
      { url: '/purchases/orders/new', name: 'new_purchase_order', title: 'New Purchase Order' },
      { url: '/purchases/payments', name: 'supplier_payments', title: 'Supplier Payments' },
      { url: '/purchases/returns', name: 'purchase_returns', title: 'Purchase Returns' },
      { url: '/purchases/debit-notes', name: 'purchase_debit_notes', title: 'Purchase Debit Notes' },
      { url: '/purchases/credit-notes', name: 'purchase_credit_notes', title: 'Purchase Credit Notes' },
      { url: '/purchases/upload', name: 'purchase_bill_upload', title: 'Purchase Bill Upload' },

      // Inventory & Warehouses
      { url: '/inventory/stock', name: 'current_stock', title: 'Current Stock' },
      { url: '/inventory/adjustments', name: 'stock_adjustments', title: 'Stock Adjustments' },
      { url: '/inventory/low-stock', name: 'low_stock', title: 'Low Stock' },
      { url: '/inventory/warehouses', name: 'warehouses', title: 'Warehouses' },
      { url: '/inventory/transfers', name: 'stock_transfers', title: 'Stock Transfers' },
      { url: '/inventory/expiry', name: 'expiry_alerts', title: 'Expiry Alerts' },
      { url: '/inventory/count', name: 'stock_count', title: 'Stock Count' },
      { url: '/inventory/serials', name: 'serials', title: 'Serials & Batches' },

      // Banking & Payments
      { url: '/payments/links', name: 'payment_links', title: 'Payment Links' },
      { url: '/payments/statements', name: 'bank_statements', title: 'Bank Statements' },
      { url: '/payments/recon', name: 'bank_recon', title: 'Bank Reconciliation' },

      // Accounting
      { url: '/accounting/chart-of-accounts', name: 'chart_of_accounts', title: 'Chart of Accounts' },
      { url: '/accounting/journals', name: 'journals', title: 'Journals' },
      { url: '/accounting/bank-recon', name: 'accounting_bank_recon', title: 'Accounting Bank Recon' },
      { url: '/accounting/cost-centers', name: 'cost_centers', title: 'Cost Centers' },

      // Financial & Compliance Reports
      { url: '/reports/sales', name: 'report_sales', title: 'Sales Report' },
      { url: '/reports/purchases', name: 'report_purchases', title: 'Purchases Report' },
      { url: '/reports/inventory', name: 'report_inventory', title: 'Inventory Report' },
      { url: '/reports/customer-ledger', name: 'report_customer_ledger', title: 'Customer Ledger' },
      { url: '/reports/supplier-ledger', name: 'report_supplier_ledger', title: 'Supplier Ledger' },
      { url: '/reports/cash-book', name: 'report_cash_book', title: 'Cash Book' },
      { url: '/reports/trial-balance', name: 'report_trial_balance', title: 'Trial Balance' },
      { url: '/reports/profit-loss', name: 'report_profit_loss', title: 'Profit & Loss' },
      { url: '/reports/balance-sheet', name: 'report_balance_sheet', title: 'Balance Sheet' },
      { url: '/reports/stock-valuation', name: 'report_stock_valuation', title: 'Stock Valuation' },
      { url: '/reports/books-health', name: 'report_books_health', title: 'Books Health' },
      { url: '/reports/gstr1', name: 'report_gstr1', title: 'GSTR-1 Report' },
      { url: '/reports/gstr3b', name: 'report_gstr3b', title: 'GSTR-3B Report' },
      { url: '/reports/gstr9', name: 'report_gstr9', title: 'GSTR-9 Report' },
      { url: '/reports/gstr2b', name: 'report_gstr2b', title: 'GSTR-2B Report' },
      { url: '/reports/gst-health', name: 'report_gst_health', title: 'GST Health' },
      { url: '/reports/statutory-events', name: 'report_statutory_events', title: 'Statutory Events' },

      // Insights
      { url: '/insights', name: 'insights_hub', title: 'Insights Hub' },
      { url: '/insights/alerts', name: 'insights_alerts', title: 'Insights Alerts' },
      { url: '/insights/health', name: 'insights_health', title: 'Business Health' },
      { url: '/insights/cashflow', name: 'insights_cashflow', title: 'Cashflow Forecast' },
      { url: '/insights/assistant', name: 'insights_assistant', title: 'AI Assistant' },

      // Settings
      { url: '/settings/units', name: 'settings_units', title: 'Units Settings' },
      { url: '/settings/templates', name: 'settings_templates', title: 'Invoice Templates' },
      { url: '/settings/users', name: 'settings_users', title: 'User Management' },
      { url: '/settings/import', name: 'settings_import', title: 'Data Import' },
      { url: '/settings/backup', name: 'settings_backup', title: 'Backup & Export' },
      { url: '/settings/billing', name: 'settings_billing', title: 'Billing & Subscription' },
      { url: '/settings/bank-accounts', name: 'settings_bank_accounts', title: 'Bank Accounts' },
      { url: '/settings/payment-gateway', name: 'settings_payment_gateway', title: 'Payment Gateway' },
      { url: '/settings/price-lists', name: 'settings_price_lists', title: 'Price Lists' },
      { url: '/settings/items', name: 'settings_items', title: 'Item Settings' },
      { url: '/settings/accounting', name: 'settings_accounting', title: 'Accounting Settings' },
      { url: '/settings/tally', name: 'settings_tally', title: 'Tally Migration' },
      { url: '/settings/ai', name: 'settings_ai', title: 'AI Settings' },
    ];

    log(`Beginning sweep across ${routesToSweep.length} routes...`);

    for (const r of routesToSweep) {
      log(`Sweeping ${r.title} (${r.url})...`);
      try {
        const resp = await page.goto(`${BASE}${r.url}`, { waitUntil: 'networkidle', timeout: 15000 });
        await page.waitForTimeout(600);
        const shotFile = `UXW2_${r.name}.png`;
        await takeScreenshot(page, shotFile);

        const currentUrl = page.url();
        const pageText = await page.locator('body').innerText();

        // Check for 404 / error / crash
        if (currentUrl.includes('/login')) {
          log(`Route ${r.url} redirected to /login (session expiry or auth gate)`);
        } else if (pageText.includes('404') || pageText.includes('Page Not Found')) {
          addFinding({
            title: `Route ${r.url} returns 404 Page Not Found`,
            module: r.url,
            type: 'Broken Flow',
            severity: 'High',
            viewport: 'Desktop',
            steps: [`Navigate to ${r.url}`],
            expected: `Renders ${r.title} page`,
            actual: 'Shows 404 Page Not Found',
            impact: 'Feature is unreachable via URL routing',
            fix: 'Add route handler in App.tsx and link navigation',
            evidence: shotFile
          });
        } else if (pageText.includes('Something went wrong') || pageText.includes('Error boundary')) {
          addFinding({
            title: `Error boundary crash on ${r.title} (${r.url})`,
            module: r.url,
            type: 'Functional',
            severity: 'Critical',
            viewport: 'Desktop',
            steps: [`Navigate to ${r.url}`],
            expected: 'Page loads without React error boundary exception',
            actual: 'Error boundary triggered on initial mount',
            impact: 'Completely blocks page usage and crashes UI',
            fix: 'Fix undefined state or missing API response handler in component',
            evidence: shotFile
          });
        }
      } catch (err) {
        log(`Failed visiting ${r.url}: ${err.message}`);
      }
    }

    // ----------------------------------------------------
    // Phase 3: Mobile Viewport Testing (375x812)
    // ----------------------------------------------------
    log('Testing Mobile Viewport (375x812)...');
    await page.setViewportSize({ width: 375, height: 812 });
    
    await page.goto(`${BASE}/`, { waitUntil: 'networkidle' });
    await page.waitForTimeout(1000);
    await takeScreenshot(page, 'UXW2_mobile_dashboard.png');

    await page.goto(`${BASE}/sales/history`, { waitUntil: 'networkidle' });
    await page.waitForTimeout(1000);
    await takeScreenshot(page, 'UXW2_mobile_sales_history.png');

    await page.goto(`${BASE}/sales/new`, { waitUntil: 'networkidle' });
    await page.waitForTimeout(1000);
    await takeScreenshot(page, 'UXW2_mobile_new_sales.png');

    // ----------------------------------------------------
    // Phase 4: Non-existent route 404 handling
    // ----------------------------------------------------
    log('Testing 404 page handling...');
    await page.goto(`${BASE}/non-existent-audit-route-404`, { waitUntil: 'networkidle' });
    await page.waitForTimeout(800);
    await takeScreenshot(page, 'UXW2_404_not_found_page.png');

  } catch (err) {
    log(`FATAL AUDIT ERROR: ${err.message}`);
  } finally {
    await browser.close();
  }

  // Save audit log & telemetry summary
  fs.writeFileSync(
    path.resolve(__dirname, 'audit_summary_wave2.json'),
    JSON.stringify({ findings, consoleErrors, networkErrors, auditLog }, null, 2)
  );

  log(`Audit run completed with ${findings.length} findings recorded.`);
}

runAudit().catch(console.error);
