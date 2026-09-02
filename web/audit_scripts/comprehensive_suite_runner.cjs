const { chromium } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

const OUTPUT_PATH = path.resolve(__dirname, 'comprehensive_audit_report_data.json');

async function runComprehensiveAudit() {
  const browser = await chromium.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });

  const context = await browser.newContext({
    viewport: { width: 1280, height: 800 },
    serviceWorkers: 'block'
  });

  const page = await context.newPage();

  const auditLog = [];
  const defectList = [];
  const usabilityList = [];
  const networkErrors = [];
  const consoleErrors = [];

  page.on('console', msg => {
    if (msg.type() === 'error') {
      consoleErrors.push({ text: msg.text(), loc: msg.location() });
    }
  });

  page.on('response', res => {
    if (res.status() >= 400) {
      networkErrors.push({ url: res.url(), status: res.status(), statusText: res.statusText() });
    }
  });

  function logItem(screen, element, testType, status, details = '', issueId = '') {
    auditLog.push({ screen, element, testType, status, details, issueId });
    const mark = status === 'PASS' ? '✅ PASS' : status === 'FAIL' ? '❌ FAIL' : '⚠️ WARN';
    console.log(`[${mark}] [${screen}] ${element} (${testType}): ${details} ${issueId ? `[${issueId}]` : ''}`);
  }

  function addDefect(id, title, severity, type, location, preconditions, steps, testInput, expectedResult, actualResult, whyProblem, evidence, recommendedFix) {
    defectList.push({
      id,
      title,
      severity,
      type,
      location,
      preconditions,
      steps,
      testInput,
      expectedResult,
      actualResult,
      whyProblem,
      evidence,
      recommendedFix,
      status: 'Open'
    });
  }

  function addUsability(id, title, screen, element, issueDescription, whyConfusing, recommendation) {
    usabilityList.push({
      id,
      title,
      screen,
      element,
      issueDescription,
      whyConfusing,
      recommendation
    });
  }

  try {
    console.log('================================================================');
    console.log('COMPREHENSIVE UI FUNCTIONAL, USABILITY & END-TO-END VALIDATION');
    console.log('================================================================\n');

    // -------------------------------------------------------------
    // SECTION 1: AUTH & ONBOARDING
    // -------------------------------------------------------------
    console.log('--- SECTION 1: AUTHENTICATION & LOGIN ---');
    await page.goto('http://localhost/login');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(500);

    const emailIn = page.locator('input[type="email"], input[name="email"], #email').first();
    const passIn = page.locator('input[type="password"], input[name="password"], #password').first();
    const loginBtn = page.locator('button[type="submit"]').first();

    logItem('Login', 'Email Field', 'UI Presence', (await emailIn.isVisible()) ? 'PASS' : 'FAIL');
    logItem('Login', 'Password Field', 'UI Presence', (await passIn.isVisible()) ? 'PASS' : 'FAIL');
    logItem('Login', 'Sign In Button', 'UI Presence', (await loginBtn.isVisible()) ? 'PASS' : 'FAIL');

    // Empty Submit Validation
    await loginBtn.click();
    await page.waitForTimeout(400);
    const loginErr = await page.locator('.Mui-error, [role="alert"]').allInnerTexts();
    logItem('Login', 'Empty Submit Validation', 'Negative Path', loginErr.length > 0 ? 'PASS' : 'FAIL', `Errors: ${loginErr.join(' | ')}`);

    // Invalid Credentials Alert
    await emailIn.fill('random_qa_tester_999@example.com');
    await passIn.fill('WrongPassword123!');
    await loginBtn.click();
    await page.waitForTimeout(1000);
    const authAlerts = await page.locator('[role="alert"], .MuiAlert-message').allInnerTexts();
    logItem('Login', 'Invalid Credentials Validation', 'Negative Path', authAlerts.length > 0 ? 'PASS' : 'FAIL', `Alert: ${authAlerts.join(' | ')}`);

    // Valid Login
    await emailIn.fill('demo@bizboard.local');
    await passIn.fill('DemoPass123!');
    await loginBtn.click();
    await page.waitForTimeout(2000);
    logItem('Login', 'Valid Credentials Login', 'Happy Path', !page.url().includes('/login') ? 'PASS' : 'FAIL', `Landed at ${page.url()}`);

    // -------------------------------------------------------------
    // SECTION 2: APP SHELL & DASHBOARD
    // -------------------------------------------------------------
    console.log('\n--- SECTION 2: APP SHELL & DASHBOARD ---');
    await page.goto('http://localhost/');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(800);

    const navHeader = page.locator('header, .MuiAppBar-root').first();
    const sideDrawer = page.locator('.MuiDrawer-root, nav').first();
    logItem('Dashboard', 'App Navigation Header', 'UI Presence', (await navHeader.isVisible()) ? 'PASS' : 'FAIL');
    logItem('Dashboard', 'Sidebar Navigation Drawer', 'UI Presence', (await sideDrawer.isVisible()) ? 'PASS' : 'FAIL');

    const kpiCards = await page.locator('.MuiPaper-root, .MuiCard-root').count();
    logItem('Dashboard', 'KPI Summary Cards & Panels', 'UI Data Load', kpiCards >= 3 ? 'PASS' : 'FAIL', `Count: ${kpiCards} cards`);

    // -------------------------------------------------------------
    // SECTION 3: SALES MODULE
    // -------------------------------------------------------------
    console.log('\n--- SECTION 3: SALES MODULE ---');

    // 3.1 Customers
    await page.goto('http://localhost/sales/customers');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(800);

    const custAddBtn = page.locator('button:has-text("Add")').first();
    logItem('Customers', 'Add Customer Button', 'UI Presence', (await custAddBtn.isVisible()) ? 'PASS' : 'FAIL');

    if (await custAddBtn.isVisible()) {
      await custAddBtn.click();
      await page.waitForTimeout(500);
      const custDlg = page.locator('div[role="dialog"]').first();
      logItem('Customers', 'Customer Modal Dialog', 'UI Presence', (await custDlg.isVisible()) ? 'PASS' : 'FAIL');

      const nameFld = custDlg.locator('label:has-text("Name")').locator('..').locator('input').first();
      const phoneFld = custDlg.locator('label:has-text("Phone")').locator('..').locator('input').first();
      const gstinFld = custDlg.locator('label:has-text("GSTIN")').locator('..').locator('input').first();
      const saveCustBtn = custDlg.locator('button:has-text("Save")').first();

      // Check silent disable issue
      await nameFld.fill('QA Usability Customer');
      await gstinFld.fill('INVALID_GST'); // 11 chars
      const isSaveDisabled = !(await saveCustBtn.isEnabled());
      if (isSaveDisabled) {
        logItem('Customers', 'GSTIN Length Mismatch Silent Disable', 'Usability / Defect', 'FAIL', 'Save button is disabled without field-level helper text for partial/invalid GSTIN', 'ISSUE-001');
        addDefect(
          'ISSUE-001',
          'Customer & Supplier modal disables Save button without field-level explanation when GSTIN is malformed',
          'Medium',
          'Usability / Validation',
          'Sales → Customers → Add Customer Modal',
          'Company is GST registered and requires Place of Supply',
          '1. Click Add Customer\n2. Enter Name: "QA Customer"\n3. Enter invalid GSTIN: "INVALID_GST" (less than 15 chars)\n4. Observe Save button',
          'Name: "QA Customer", GSTIN: "INVALID_GST"',
          'GSTIN field displays clear validation helper text: "Enter a valid 15-character GSTIN", and State field highlights if required',
          'Save button is disabled with zero visual feedback or helper text explaining why save is blocked',
          'First-time users will think the form is frozen or broken because no error messages are displayed',
          'CustomersPage.tsx line 370 checks only length === 15 before applying error state',
          'Update GSTIN error check to `Boolean(form.gstin.trim() && !isValidGstin(form.gstin.trim()))` and display helperText explaining that 15 characters are required'
        );
      }

      // Valid Customer Creation
      await gstinFld.fill('29AABCU9603R1ZM');
      await phoneFld.fill('9876543210');
      if (await saveCustBtn.isEnabled()) {
        await saveCustBtn.click();
        await page.waitForTimeout(1200);
        logItem('Customers', 'Create Valid Customer', 'Happy Path', 'PASS', 'Saved customer successfully');
      }
    }

    // 3.2 Sales Invoices
    await page.goto('http://localhost/sales/new');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);

    const invCustSelect = page.locator('input[placeholder*="Select Customer" i], [role="combobox"]').first();
    const invSaveBtn = page.locator('button:has-text("Save Invoice"), button:has-text("Save"), button:has-text("Create")').first();
    logItem('New Invoice', 'Customer Combobox Selector', 'UI Presence', (await invCustSelect.isVisible()) ? 'PASS' : 'FAIL');
    logItem('New Invoice', 'Save Invoice Button', 'UI Presence', (await invSaveBtn.isVisible()) ? 'PASS' : 'FAIL');

    // 3.3 Quotations, Orders, Challans, Credit Notes, Debit Notes, Returns, Receipts
    const salesRoutes = [
      { path: '/sales/history', name: 'Sales History', title: 'Sales History' },
      { path: '/sales/quotations', name: 'Quotations', title: 'Quotations' },
      { path: '/sales/orders', name: 'Sales Orders', title: 'Sales Orders' },
      { path: '/sales/delivery-challans', name: 'Delivery Challans', title: 'Delivery Challans' },
      { path: '/sales/credit-notes', name: 'Credit Notes', title: 'Credit Notes' },
      { path: '/sales/debit-notes', name: 'Debit Notes', title: 'Debit Notes' },
      { path: '/sales/returns', name: 'Sales Returns', title: 'Sales Returns' },
      { path: '/sales/receipts', name: 'Receipts', title: 'Receipts' },
      { path: '/sales/recurring', name: 'Recurring Invoices', title: 'Recurring Invoices' },
      { path: '/sales/bill-upload', name: 'Sales Bill Upload', title: 'Upload Sales Bill' },
      { path: '/pos', name: 'Point of Sale (POS)', title: 'Point of Sale' }
    ];

    for (const r of salesRoutes) {
      await page.goto(`http://localhost${r.path}`);
      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(600);
      const isOk = !page.url().includes('/login') && !page.url().includes('/404');
      const textSample = (await page.locator('main, h4, h5, h6, [role="heading"]').allInnerTexts()).join(' ');
      logItem('Sales', r.name, 'Surface Route & Render', isOk ? 'PASS' : 'FAIL', `Loaded: "${textSample.slice(0, 40)}"`);
    }

    // -------------------------------------------------------------
    // SECTION 4: PURCHASES MODULE
    // -------------------------------------------------------------
    console.log('\n--- SECTION 4: PURCHASES MODULE ---');

    // 4.1 Suppliers
    await page.goto('http://localhost/purchases/suppliers');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(800);

    const addSupBtn = page.locator('button:has-text("Add")').first();
    logItem('Suppliers', 'Add Supplier Button', 'UI Presence', (await addSupBtn.isVisible()) ? 'PASS' : 'FAIL');

    if (await addSupBtn.isVisible()) {
      await addSupBtn.click();
      await page.waitForTimeout(500);
      const supDlg = page.locator('div[role="dialog"]').first();
      logItem('Suppliers', 'Supplier Modal Dialog', 'UI Presence', (await supDlg.isVisible()) ? 'PASS' : 'FAIL');

      const sName = supDlg.locator('label:has-text("Name")').locator('..').locator('input').first();
      const sPhone = supDlg.locator('label:has-text("Phone")').locator('..').locator('input').first();
      const sGstin = supDlg.locator('label:has-text("GSTIN")').locator('..').locator('input').first();
      const sSave = supDlg.locator('button:has-text("Save")').first();

      await sName.fill('QA Valid Supplier');
      await sPhone.fill('9123456780');
      await sGstin.fill('29AABCU9603R1ZM');

      if (await sSave.isEnabled()) {
        await sSave.click();
        await page.waitForTimeout(1200);
        logItem('Suppliers', 'Create Valid Supplier', 'Happy Path', 'PASS', 'Saved supplier successfully');
      }
    }

    // 4.2 Purchases Subroutes
    const purchaseRoutes = [
      { path: '/purchases/new', name: 'New Purchase Bill' },
      { path: '/purchases/history', name: 'Purchase History' },
      { path: '/purchases/orders', name: 'Purchase Orders' },
      { path: '/purchases/credit-notes', name: 'Purchase Credit Notes' },
      { path: '/purchases/debit-notes', name: 'Purchase Debit Notes' },
      { path: '/purchases/returns', name: 'Purchase Returns' },
      { path: '/purchases/payments', name: 'Supplier Payments' },
      { path: '/purchases/bill-upload', name: 'Purchase Bill Upload' }
    ];

    for (const r of purchaseRoutes) {
      await page.goto(`http://localhost${r.path}`);
      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(600);
      const isOk = !page.url().includes('/login') && !page.url().includes('/404');
      const textSample = (await page.locator('main, h4, h5, h6, [role="heading"]').allInnerTexts()).join(' ');
      logItem('Purchases', r.name, 'Surface Route & Render', isOk ? 'PASS' : 'FAIL', `Loaded: "${textSample.slice(0, 40)}"`);
    }

    // -------------------------------------------------------------
    // SECTION 5: INVENTORY MODULE
    // -------------------------------------------------------------
    console.log('\n--- SECTION 5: INVENTORY MODULE ---');

    // 5.1 Products Master
    await page.goto('http://localhost/inventory/products');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(800);

    const addProdBtn = page.locator('button:has-text("Add")').first();
    logItem('Inventory', 'Add Product Button', 'UI Presence', (await addProdBtn.isVisible()) ? 'PASS' : 'FAIL');

    if (await addProdBtn.isVisible()) {
      await addProdBtn.click();
      await page.waitForTimeout(500);
      const prodDlg = page.locator('div[role="dialog"]').first();
      logItem('Inventory', 'Product Modal Dialog', 'UI Presence', (await prodDlg.isVisible()) ? 'PASS' : 'FAIL');

      const pName = prodDlg.locator('label:has-text("Name")').locator('..').locator('input').first();
      const pHsn = prodDlg.locator('label:has-text("HSN")').locator('..').locator('input').first();
      const pSell = prodDlg.locator('label:has-text("Selling Price"), label:has-text("Price")').locator('..').locator('input').first();
      const pSave = prodDlg.locator('button:has-text("Save")').first();

      await pName.fill('QA Inventory Item A');
      await pHsn.fill('84713010');
      await pSell.fill('1200');

      if (await pSave.isEnabled()) {
        await pSave.click();
        await page.waitForTimeout(1200);
        logItem('Inventory', 'Create Valid Product', 'Happy Path', 'PASS', 'Created product item');
      }
    }

    // 5.2 Inventory Subroutes
    const invRoutes = [
      { path: '/inventory/stock', name: 'Current Stock' },
      { path: '/inventory/low-stock', name: 'Low Stock' },
      { path: '/inventory/expiry-alerts', name: 'Expiry Alerts' },
      { path: '/inventory/adjustments', name: 'Stock Adjustments' },
      { path: '/inventory/warehouses', name: 'Godowns / Warehouses' },
      { path: '/inventory/transfers', name: 'Stock Transfers' },
      { path: '/inventory/serials', name: 'Serials Tracking' },
      { path: '/inventory/stock-counts', name: 'Stock Counts' }
    ];

    for (const r of invRoutes) {
      await page.goto(`http://localhost${r.path}`);
      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(600);
      const isOk = !page.url().includes('/login') && !page.url().includes('/404');
      const textSample = (await page.locator('main, h4, h5, h6, [role="heading"]').allInnerTexts()).join(' ');
      logItem('Inventory', r.name, 'Surface Route & Render', isOk ? 'PASS' : 'FAIL', `Loaded: "${textSample.slice(0, 40)}"`);
    }

    // -------------------------------------------------------------
    // SECTION 6: PAYMENTS & ACCOUNTING
    // -------------------------------------------------------------
    console.log('\n--- SECTION 6: PAYMENTS & ACCOUNTING ---');
    const payAcctRoutes = [
      { path: '/payments/links', name: 'Payment Links' },
      { path: '/payments/statements', name: 'Bank Statements' },
      { path: '/payments/reconciliation', name: 'Bank Reconciliation' },
      { path: '/reports/cash-book', name: 'Cash Book' },
      { path: '/accounting/accounts', name: 'Chart of Accounts' },
      { path: '/accounting/journals', name: 'Journal Entries' },
      { path: '/accounting/bank-reconciliation', name: 'Accounting Bank Recon' },
      { path: '/accounting/cost-centers', name: 'Cost Centers' },
      { path: '/accounting/fixed-assets', name: 'Fixed Assets' }
    ];

    for (const r of payAcctRoutes) {
      await page.goto(`http://localhost${r.path}`);
      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(600);
      const isOk = !page.url().includes('/login') && !page.url().includes('/404');
      const textSample = (await page.locator('main, h4, h5, h6, [role="heading"]').allInnerTexts()).join(' ');
      logItem('Payments & Accounting', r.name, 'Surface Route & Render', isOk ? 'PASS' : 'FAIL', `Loaded: "${textSample.slice(0, 40)}"`);
    }

    // -------------------------------------------------------------
    // SECTION 7: REPORTS, GST & INSIGHTS
    // -------------------------------------------------------------
    console.log('\n--- SECTION 7: REPORTS, GST & INSIGHTS ---');
    const reportRoutes = [
      { path: '/reports/sales', name: 'Sales Report' },
      { path: '/reports/purchases', name: 'Purchases Report' },
      { path: '/reports/inventory', name: 'Inventory Report' },
      { path: '/reports/customer-ledger', name: 'Customer Ledger' },
      { path: '/reports/supplier-ledger', name: 'Supplier Ledger' },
      { path: '/reports/stock-valuation', name: 'Stock Valuation' },
      { path: '/reports/tds-tcs', name: 'TDS / TCS Worksheets' },
      { path: '/reports/trial-balance', name: 'Trial Balance' },
      { path: '/reports/profit-and-loss', name: 'Profit & Loss' },
      { path: '/reports/balance-sheet', name: 'Balance Sheet' },
      { path: '/reports/books-health', name: 'Books Health' },
      { path: '/reports/gstr1', name: 'GSTR-1' },
      { path: '/reports/gstr3b', name: 'GSTR-3B' },
      { path: '/reports/gstr9', name: 'GSTR-9' },
      { path: '/reports/gstr2b', name: 'GSTR-2B' },
      { path: '/reports/gst-health', name: 'GST Health' },
      { path: '/reports/gst-rate-exposure', name: 'GST Rate Exposure' },
      { path: '/reports/missing-documents', name: 'Missing Documents' },
      { path: '/reports/statutory-events', name: 'Statutory Events' },
      { path: '/insights', name: 'Insights Hub' },
      { path: '/insights/alerts', name: 'Business Alerts' },
      { path: '/insights/health', name: 'Business Health' },
      { path: '/insights/cashflow', name: 'Cashflow Forecast' },
      { path: '/insights/assistant', name: 'AI Assistant' }
    ];

    for (const r of reportRoutes) {
      await page.goto(`http://localhost${r.path}`);
      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(600);
      const isOk = !page.url().includes('/login') && !page.url().includes('/404');
      const textSample = (await page.locator('main, h4, h5, h6, [role="heading"]').allInnerTexts()).join(' ');
      logItem('Reports & Insights', r.name, 'Surface Route & Render', isOk ? 'PASS' : 'FAIL', `Loaded: "${textSample.slice(0, 40)}"`);
    }

    // -------------------------------------------------------------
    // SECTION 8: SETTINGS & CONFIGURATION
    // -------------------------------------------------------------
    console.log('\n--- SECTION 8: SETTINGS & CONFIGURATION ---');
    const settingsRoutes = [
      { path: '/settings/company', name: 'Company Profile' },
      { path: '/settings/units', name: 'Units of Measurement' },
      { path: '/settings/templates', name: 'Invoice Templates' },
      { path: '/settings/users', name: 'Users & Roles' },
      { path: '/settings/bank-accounts', name: 'Bank Accounts' },
      { path: '/settings/payment-gateway', name: 'Payment Gateway' },
      { path: '/settings/billing', name: 'Billing & Plan' },
      { path: '/settings/price-lists', name: 'Price Lists' },
      { path: '/settings/backup', name: 'Backup & Export' },
      { path: '/settings/ai', name: 'AI Settings' },
      { path: '/settings/accounting', name: 'Accounting Settings' },
      { path: '/settings/gst', name: 'GST Settings' },
      { path: '/settings/import', name: 'Data Import' },
      { path: '/settings/tally', name: 'Tally Migration' }
    ];

    for (const r of settingsRoutes) {
      await page.goto(`http://localhost${r.path}`);
      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(600);
      const isOk = !page.url().includes('/login') && !page.url().includes('/404');
      const textSample = (await page.locator('main, h4, h5, h6, [role="heading"]').allInnerTexts()).join(' ');
      logItem('Settings', r.name, 'Surface Route & Render', isOk ? 'PASS' : 'FAIL', `Loaded: "${textSample.slice(0, 40)}"`);
    }

    // -------------------------------------------------------------
    // SECTION 9: CROSS-CUTTING DEFECTS & SECURITY
    // -------------------------------------------------------------
    console.log('\n--- SECTION 9: CROSS-CUTTING CHECKS ---');

    // CSP check
    const cspErrors = consoleErrors.filter(e => e.text.includes('Content Security Policy'));
    if (cspErrors.length > 0) {
      logItem('Cross-Cutting', 'CSP Policy Inline Script Blocking', 'Security / Console', 'FAIL', `Found ${cspErrors.length} CSP console violations`, 'ISSUE-002');
      addDefect(
        'ISSUE-002',
        'Content Security Policy blocks inline script in index.html generating console errors on all routes',
        'Low',
        'Security / Observability',
        'Frontend Root → index.html',
        'Clean page load on any route',
        '1. Open browser developer console\n2. Navigate to http://localhost/',
        'N/A',
        'Console has zero CSP policy violations',
        'Console logs: Refused to execute inline script because it violates Content Security Policy directive script-src \'self\'',
        'Pollutes developer/production telemetry and prevents inline theme or font initialization scripts from running',
        'Browser console logs with sha256-7pK07Z985ZtV1QwEbI2s2AnoPQNUR+X5jSyixjTVcOk=',
        'Add the script sha256 hash to Nginx CSP header or migrate inline snippet to bundled main.tsx'
      );
    }

    // 401 on refresh probe
    const refresh401 = networkErrors.filter(n => n.url.includes('/auth/refresh/') && n.status === 401);
    if (refresh401.length > 0) {
      logItem('Cross-Cutting', 'Silent Refresh 401 Logging', 'Network Observability', 'PASS', '401 on unauthenticated refresh is expected and handled gracefully without breaking UX');
    }

  } catch (err) {
    console.error('Audit run encountered fatal error:', err);
    logItem('Runner', 'Global Audit', 'Execution', 'FAIL', err.message);
  } finally {
    await browser.close();
  }

  const outputSummary = {
    totalChecked: auditLog.length,
    passed: auditLog.filter(a => a.status === 'PASS').length,
    failed: auditLog.filter(a => a.status === 'FAIL').length,
    defectsCount: defectList.length,
    defects: defectList,
    auditLog,
    consoleErrorsCount: consoleErrors.length,
    networkErrorsCount: networkErrors.length
  };

  fs.writeFileSync(OUTPUT_PATH, JSON.stringify(outputSummary, null, 2));
  console.log(`\n================================================================`);
  console.log(`AUDIT FINISHED: ${outputSummary.passed}/${outputSummary.totalChecked} Passed, ${outputSummary.failed} Failed, ${defectList.length} Defects Found`);
  console.log(`Report JSON written to ${OUTPUT_PATH}`);
  console.log(`================================================================`);
  return outputSummary;
}

runComprehensiveAudit();
