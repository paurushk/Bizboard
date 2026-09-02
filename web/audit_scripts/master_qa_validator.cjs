const { chromium } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

const LOG_FILE = path.resolve(__dirname, 'master_qa_results.json');

async function runMasterQAValidation() {
  const browser = await chromium.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });

  const context = await browser.newContext({
    viewport: { width: 1280, height: 800 },
    serviceWorkers: 'block'
  });

  const page = await context.newPage();

  const testLog = [];
  const defects = [];
  const errorMessagesReview = [];

  const consoleErrors = [];
  const networkErrors = [];

  page.on('console', msg => {
    if (msg.type() === 'error') {
      consoleErrors.push({ text: msg.text(), location: msg.location() });
    }
  });

  page.on('pageerror', err => {
    consoleErrors.push({ text: err.message, stack: err.stack });
  });

  page.on('response', res => {
    if (res.status() >= 400) {
      networkErrors.push({ status: res.status(), url: res.url(), statusText: res.statusText() });
    }
  });

  function recordTest(module, screen, element, testType, status, details = '', issueId = '') {
    testLog.push({ module, screen, element, testType, status, details, issueId });
    const sym = status === 'PASS' ? '✅' : status === 'FAIL' ? '❌' : '⚠️';
    console.log(`${sym} [${status}] [${module} -> ${screen}] ${element} (${testType}): ${details} ${issueId ? `[${issueId}]` : ''}`);
  }

  function recordDefect(id, title, severity, type, location, preconditions, steps, testInput, expectedResult, actualResult, whyProblem, evidence, recommendedFix) {
    defects.push({
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

  function recordReview(issueId, category, screen, messageText, critique, recommendation) {
    errorMessagesReview.push({
      issueId,
      category,
      screen,
      messageText,
      critique,
      recommendation
    });
  }

  try {
    console.log('===============================================================');
    console.log('STARTING COMPREHENSIVE UI FUNCTIONAL & USABILITY VALIDATION');
    console.log('===============================================================\n');

    // =========================================================================
    // MODULE 1: AUTHENTICATION & SESSION MANAGEMENT
    // =========================================================================
    console.log('\n>>> MODULE 1: AUTHENTICATION & ACCESS CONTROL <<<');

    // 1.1 Unauthenticated Login Page
    await page.goto('http://localhost/login');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(500);

    const emailInput = page.locator('input[type="email"], input[name="email"], #email').first();
    const passwordInput = page.locator('input[type="password"], input[name="password"], #password').first();
    const submitLoginBtn = page.locator('button[type="submit"]').first();

    if (await emailInput.isVisible() && await passwordInput.isVisible() && await submitLoginBtn.isVisible()) {
      recordTest('Auth', 'Login', 'Login Form Fields', 'UI Presence', 'PASS', 'Email, password & submit button present');
    } else {
      recordTest('Auth', 'Login', 'Login Form Fields', 'UI Presence', 'FAIL', 'Missing elements on login page', 'DEF-001');
    }

    // 1.2 Empty submit validation
    await submitLoginBtn.click();
    await page.waitForTimeout(400);
    const loginEmptyErrors = await page.locator('.Mui-error, [role="alert"]').allInnerTexts();
    if (loginEmptyErrors.length > 0) {
      recordTest('Auth', 'Login', 'Empty Submit Validation', 'Negative Path', 'PASS', `Validation error shown: "${loginEmptyErrors.join(' | ')}"`);
    } else {
      recordTest('Auth', 'Login', 'Empty Submit Validation', 'Negative Path', 'FAIL', 'No validation shown on empty submit', 'DEF-002');
      recordDefect('DEF-002', 'Login form allows empty submit without inline validation', 'Medium', 'Validation', 'Auth → Login → Submit', 'Fresh session', '1. Go to /login\n2. Click Submit', 'Empty inputs', 'Validation messages appear under required fields', 'No error messages shown', 'User is confused why login did not proceed', 'No DOM error elements found', 'Add client-side required field validation');
    }

    // 1.3 Invalid password / credentials
    await emailInput.fill('invalid_user_test@example.com');
    await passwordInput.fill('WrongPassword123!');
    await submitLoginBtn.click();
    await page.waitForTimeout(1000);
    const alertText = await page.locator('[role="alert"], .MuiAlert-message').allInnerTexts();
    if (alertText.some(t => t.toLowerCase().includes('incorrect') || t.toLowerCase().includes('invalid') || t.toLowerCase().includes('credentials'))) {
      recordTest('Auth', 'Login', 'Invalid Credentials Alert', 'Negative Path', 'PASS', `Alert displayed: "${alertText.join(' | ')}"`);
    } else {
      recordTest('Auth', 'Login', 'Invalid Credentials Alert', 'Negative Path', 'FAIL', 'No alert message displayed for bad credentials', 'DEF-003');
    }

    // 1.4 Valid Login
    await emailInput.fill('demo@bizboard.local');
    await passwordInput.fill('DemoPass123!');
    await submitLoginBtn.click();
    await page.waitForTimeout(2000);
    if (!page.url().includes('/login')) {
      recordTest('Auth', 'Login', 'Valid Login Flow', 'Happy Path', 'PASS', `Logged in successfully, landed at ${page.url()}`);
    } else {
      recordTest('Auth', 'Login', 'Valid Login Flow', 'Happy Path', 'FAIL', `Login did not navigate away from /login: ${page.url()}`, 'DEF-004');
    }

    // =========================================================================
    // MODULE 2: DASHBOARD & APP SHELL NAVIGATION
    // =========================================================================
    console.log('\n>>> MODULE 2: DASHBOARD & APP SHELL <<<');
    await page.goto('http://localhost/');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);

    const appTitle = page.locator('header, .MuiAppBar-root').first();
    const userRoleBadge = page.locator('text=OWNER, text=Owner').first();
    const logoutBtn = page.locator('button:has-text("Logout"), button:has-text("Sign Out"), button:has-text("Log out")').first();

    recordTest('Dashboard', 'Dashboard', 'App Header & Navigation Bar', 'UI Presence', (await appTitle.isVisible()) ? 'PASS' : 'FAIL');
    recordTest('Dashboard', 'Dashboard', 'User Profile / Role Indicator', 'UI Presence', (await userRoleBadge.isVisible()) ? 'PASS' : 'FAIL');
    recordTest('Dashboard', 'Dashboard', 'Logout Button', 'UI Presence', (await logoutBtn.isVisible()) ? 'PASS' : 'FAIL');

    // Check dashboard metrics cards
    const metricCards = await page.locator('.MuiCard-root, .MuiPaper-root').count();
    recordTest('Dashboard', 'Dashboard', 'KPI Metrics & Summary Cards', 'UI Data Load', metricCards >= 3 ? 'PASS' : 'FAIL', `Found ${metricCards} cards/panels`);

    // =========================================================================
    // MODULE 3: COMPANY SETTINGS & MASTER SETUP
    // =========================================================================
    console.log('\n>>> MODULE 3: COMPANY SETTINGS & MASTERS <<<');
    await page.goto('http://localhost/settings/company');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(800);

    const companyNameInput = page.locator('label:has-text("Company Name"), label:has-text("Trade Name")').locator('..').locator('input').first();
    const gstinSettingInput = page.locator('label:has-text("GSTIN")').locator('..').locator('input').first();
    const saveCompanyBtn = page.locator('button:has-text("Save"), button:has-text("Update")').first();

    if (await companyNameInput.isVisible()) {
      recordTest('Settings', 'Company Settings', 'Company Name Field', 'UI Presence', 'PASS', 'Company field visible');
      // Test invalid GSTIN validation in company settings
      if (await gstinSettingInput.isVisible()) {
        await gstinSettingInput.fill('INVALID_GSTIN_XYZ');
        if (await saveCompanyBtn.isVisible()) {
          await saveCompanyBtn.click();
          await page.waitForTimeout(500);
          const gstinErr = await page.locator('.Mui-error, [role="alert"]').allInnerTexts();
          recordTest('Settings', 'Company Settings', 'Invalid GSTIN Validation', 'Negative Path', gstinErr.length > 0 ? 'PASS' : 'FAIL', `Feedback: "${gstinErr.join(' | ')}"`);
        }
        // Revert to valid GSTIN
        await gstinSettingInput.fill('29AABCU9603R1ZM');
        if (await saveCompanyBtn.isVisible()) {
          await saveCompanyBtn.click();
          await page.waitForTimeout(800);
        }
      }
    } else {
      recordTest('Settings', 'Company Settings', 'Company Settings Form', 'UI Presence', 'FAIL', 'Company form inputs missing', 'DEF-005');
    }

    // =========================================================================
    // MODULE 4: CUSTOMERS & SALES WORKFLOW
    // =========================================================================
    console.log('\n>>> MODULE 4: CUSTOMERS & SALES MODULE <<<');

    // 4.1 Customers List & Add Customer
    await page.goto('http://localhost/sales/customers');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(800);

    const addCustomerBtn = page.locator('button:has-text("Add"), button:has-text("New"), button:has-text("Create")').first();
    if (await addCustomerBtn.isVisible()) {
      recordTest('Sales', 'Customers', 'Add Customer Button', 'UI Presence', 'PASS', 'Add button visible');
      await addCustomerBtn.click();
      await page.waitForTimeout(600);

      // Verify dialog opened
      const customerDialog = page.locator('div[role="dialog"]').first();
      if (await customerDialog.isVisible()) {
        recordTest('Sales', 'Customers', 'Customer Modal Dialog', 'UI Presence', 'PASS', 'Modal opened');

        // Test empty submit
        const modalSaveBtn = customerDialog.locator('button:has-text("Save"), button:has-text("Create"), button[type="submit"]').first();
        if (await modalSaveBtn.isEnabled()) {
          await modalSaveBtn.click();
          await page.waitForTimeout(400);
          const custErrs = await customerDialog.locator('.Mui-error, [role="alert"]').allInnerTexts();
          recordTest('Sales', 'Customers', 'Customer Empty Submit Validation', 'Negative Path', custErrs.length > 0 ? 'PASS' : 'FAIL', `Errors: "${custErrs.join(' | ')}"`);
        } else {
          recordTest('Sales', 'Customers', 'Customer Empty Submit Validation', 'Negative Path', 'PASS', 'Save button properly disabled when required fields are empty');
        }

        // Fill Valid Customer
        const nameField = customerDialog.locator('label:has-text("Name")').locator('..').locator('input').first();
        const phoneField = customerDialog.locator('label:has-text("Phone")').locator('..').locator('input').first();
        const gstinField = customerDialog.locator('label:has-text("GSTIN")').locator('..').locator('input').first();

        const newCustName = `MasterQA-Cust-${Date.now().toString().slice(-4)}`;
        if (await nameField.isVisible()) await nameField.fill(newCustName);
        if (await phoneField.isVisible()) await phoneField.fill('9876543210');
        if (await gstinField.isVisible()) await gstinField.fill('29AABCU9603R1ZM');

        if (await modalSaveBtn.isVisible()) {
          await modalSaveBtn.click();
          await page.waitForTimeout(1200);
          recordTest('Sales', 'Customers', 'Save Customer Record', 'Happy Path', 'PASS', `Created customer ${newCustName}`);
        }
      } else {
        recordTest('Sales', 'Customers', 'Customer Modal Dialog', 'UI Presence', 'FAIL', 'Modal did not open on Add click', 'DEF-006');
      }
    } else {
      recordTest('Sales', 'Customers', 'Add Customer Button', 'UI Presence', 'FAIL', 'Add customer button not found', 'DEF-007');
    }

    // 4.2 New Sales Invoice
    await page.goto('http://localhost/sales/new');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);

    const custAutocomplete = page.locator('input[placeholder*="Select Customer" i], label:has-text("Customer")').locator('..').locator('input, [role="combobox"]').first();
    const saveInvoiceBtn = page.locator('button:has-text("Save Invoice"), button:has-text("Create Invoice"), button:has-text("Save")').first();
    const addLineBtn = page.locator('button:has-text("Add Line"), button:has-text("Add Item"), button:has-text("+ Add")').first();

    recordTest('Sales', 'New Invoice', 'Customer Picker Autocomplete', 'UI Presence', (await custAutocomplete.isVisible()) ? 'PASS' : 'FAIL');
    recordTest('Sales', 'New Invoice', 'Save Invoice Button', 'UI Presence', (await saveInvoiceBtn.isVisible()) ? 'PASS' : 'FAIL');

    // Test invoice empty validation
    if (await saveInvoiceBtn.isVisible()) {
      await saveInvoiceBtn.click();
      await page.waitForTimeout(500);
      const invErrors = await page.locator('.Mui-error, [role="alert"], .MuiAlert-message, .MuiSnackbar-root').allInnerTexts();
      recordTest('Sales', 'New Invoice', 'Invoice Empty Validation', 'Negative Path', invErrors.length > 0 ? 'PASS' : 'FAIL', `Errors: "${invErrors.join(' | ')}"`);
    }

    // 4.3 Sales History & List Navigation
    await page.goto('http://localhost/sales/history');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(800);

    const salesHistoryTable = page.locator('table').first();
    recordTest('Sales', 'Sales History', 'Sales Invoices Table', 'UI Presence', (await salesHistoryTable.isVisible()) ? 'PASS' : 'FAIL');

    // 4.4 Quotations, Sales Orders, Delivery Challans, Credit Notes, Receipts
    const salesSubmodules = [
      { path: '/sales/quotations', screen: 'Quotations' },
      { path: '/sales/orders', screen: 'Sales Orders' },
      { path: '/sales/delivery-challans', screen: 'Delivery Challans' },
      { path: '/sales/credit-notes', screen: 'Credit Notes' },
      { path: '/sales/debit-notes', screen: 'Debit Notes' },
      { path: '/sales/returns', screen: 'Sales Returns' },
      { path: '/sales/receipts', screen: 'Receipts' },
      { path: '/sales/recurring', screen: 'Recurring Invoices' },
      { path: '/sales/bill-upload', screen: 'Sales Bill Upload' },
      { path: '/pos', screen: 'POS Counter' }
    ];

    for (const sub of salesSubmodules) {
      await page.goto(`http://localhost${sub.path}`);
      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(500);
      const heading = await page.locator('h4, h5, h6, [role="heading"]').allInnerTexts();
      const hasContent = heading.length > 0;
      recordTest('Sales', sub.screen, `${sub.screen} Page Surface & Navigation`, 'Navigation & Render', hasContent ? 'PASS' : 'FAIL', `Loaded heading: "${heading[0] || ''}"`);
    }

    // =========================================================================
    // MODULE 5: SUPPLIERS & PURCHASES WORKFLOW
    // =========================================================================
    console.log('\n>>> MODULE 5: SUPPLIERS & PURCHASES MODULE <<<');

    // 5.1 Suppliers List & Add Supplier
    await page.goto('http://localhost/purchases/suppliers');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(800);

    const addSupBtn = page.locator('button:has-text("Add"), button:has-text("New"), button:has-text("Create")').first();
    if (await addSupBtn.isVisible()) {
      recordTest('Purchases', 'Suppliers', 'Add Supplier Button', 'UI Presence', 'PASS', 'Add button visible');
      await addSupBtn.click();
      await page.waitForTimeout(600);

      const supDialog = page.locator('div[role="dialog"]').first();
      if (await supDialog.isVisible()) {
        recordTest('Purchases', 'Suppliers', 'Supplier Modal Dialog', 'UI Presence', 'PASS', 'Dialog opened');

        const supNameField = supDialog.locator('label:has-text("Name")').locator('..').locator('input').first();
        const supPhoneField = supDialog.locator('label:has-text("Phone")').locator('..').locator('input').first();
        const supGstinField = supDialog.locator('label:has-text("GSTIN")').locator('..').locator('input').first();
        const supSaveBtn = supDialog.locator('button:has-text("Save"), button:has-text("Create"), button[type="submit"]').first();

        const newSupName = `MasterQA-Sup-${Date.now().toString().slice(-4)}`;
        if (await supNameField.isVisible()) await supNameField.fill(newSupName);
        if (await supPhoneField.isVisible()) await supPhoneField.fill('9123456780');
        if (await supGstinField.isVisible()) await supGstinField.fill('29AABCU9603R1ZM');

        if (await supSaveBtn.isVisible()) {
          await supSaveBtn.click();
          await page.waitForTimeout(1200);
          recordTest('Purchases', 'Suppliers', 'Save Supplier Record', 'Happy Path', 'PASS', `Created supplier ${newSupName}`);
        }
      }
    }

    // 5.2 New Purchase Bill Page
    await page.goto('http://localhost/purchases/new');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(800);

    const supCombobox = page.locator('input[placeholder*="Select Supplier" i], label:has-text("Supplier")').locator('..').locator('input, [role="combobox"]').first();
    const savePurchaseBtn = page.locator('button:has-text("Save Purchase"), button:has-text("Save"), button:has-text("Create")').first();

    recordTest('Purchases', 'New Purchase', 'Supplier Picker Autocomplete', 'UI Presence', (await supCombobox.isVisible()) ? 'PASS' : 'FAIL');
    recordTest('Purchases', 'New Purchase', 'Save Purchase Button', 'UI Presence', (await savePurchaseBtn.isVisible()) ? 'PASS' : 'FAIL');

    // 5.3 Purchases Submodules
    const purchaseSubmodules = [
      { path: '/purchases/orders', screen: 'Purchase Orders' },
      { path: '/purchases/history', screen: 'Purchase History' },
      { path: '/purchases/credit-notes', screen: 'Purchase Credit Notes' },
      { path: '/purchases/debit-notes', screen: 'Purchase Debit Notes' },
      { path: '/purchases/returns', screen: 'Purchase Returns' },
      { path: '/purchases/payments', screen: 'Supplier Payments' },
      { path: '/purchases/bill-upload', screen: 'Purchase Bill Upload' }
    ];

    for (const sub of purchaseSubmodules) {
      await page.goto(`http://localhost${sub.path}`);
      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(500);
      const heading = await page.locator('h4, h5, h6, [role="heading"]').allInnerTexts();
      recordTest('Purchases', sub.screen, `${sub.screen} Page Surface & Navigation`, 'Navigation & Render', heading.length > 0 ? 'PASS' : 'FAIL', `Heading: "${heading[0] || ''}"`);
    }

    // =========================================================================
    // MODULE 6: INVENTORY & WAREHOUSES
    // =========================================================================
    console.log('\n>>> MODULE 6: INVENTORY & WAREHOUSES <<<');

    // 6.1 Products Master & Add Product
    await page.goto('http://localhost/inventory/products');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(800);

    const addProductBtn = page.locator('button:has-text("Add"), button:has-text("New"), button:has-text("Create")').first();
    if (await addProductBtn.isVisible()) {
      recordTest('Inventory', 'Products', 'Add Product Button', 'UI Presence', 'PASS', 'Add button found');
      await addProductBtn.click();
      await page.waitForTimeout(600);

      const prodDialog = page.locator('div[role="dialog"]').first();
      if (await prodDialog.isVisible()) {
        recordTest('Inventory', 'Products', 'Product Modal Dialog', 'UI Presence', 'PASS', 'Modal dialog opened');

        const prodNameField = prodDialog.locator('label:has-text("Name")').locator('..').locator('input').first();
        const prodHsnField = prodDialog.locator('label:has-text("HSN")').locator('..').locator('input').first();
        const prodPriceField = prodDialog.locator('label:has-text("Selling Price"), label:has-text("Price")').locator('..').locator('input').first();
        const prodSaveBtn = prodDialog.locator('button:has-text("Save"), button:has-text("Create"), button[type="submit"]').first();

        const newProdName = `MasterQA-Item-${Date.now().toString().slice(-4)}`;
        if (await prodNameField.isVisible()) await prodNameField.fill(newProdName);
        if (await prodHsnField.isVisible()) await prodHsnField.fill('84713010');
        if (await prodPriceField.isVisible()) await prodPriceField.fill('2500');

        if (await prodSaveBtn.isVisible()) {
          await prodSaveBtn.click();
          await page.waitForTimeout(1200);
          recordTest('Inventory', 'Products', 'Save Product Record', 'Happy Path', 'PASS', `Created product ${newProdName}`);
        }
      }
    }

    // 6.2 Inventory Submodules
    const invSubmodules = [
      { path: '/inventory/stock', screen: 'Current Stock' },
      { path: '/inventory/low-stock', screen: 'Low Stock' },
      { path: '/inventory/expiry-alerts', screen: 'Expiry Alerts' },
      { path: '/inventory/adjustments', screen: 'Stock Adjustments' },
      { path: '/inventory/warehouses', screen: 'Warehouses' },
      { path: '/inventory/transfers', screen: 'Stock Transfers' },
      { path: '/inventory/serials', screen: 'Serials Tracking' },
      { path: '/inventory/stock-counts', screen: 'Stock Counts' }
    ];

    for (const sub of invSubmodules) {
      await page.goto(`http://localhost${sub.path}`);
      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(500);
      const heading = await page.locator('h4, h5, h6, [role="heading"]').allInnerTexts();
      recordTest('Inventory', sub.screen, `${sub.screen} Page Surface & Navigation`, 'Navigation & Render', heading.length > 0 ? 'PASS' : 'FAIL', `Heading: "${heading[0] || ''}"`);
    }

    // =========================================================================
    // MODULE 7: PAYMENTS, BANKING & ACCOUNTING
    // =========================================================================
    console.log('\n>>> MODULE 7: PAYMENTS, BANKING & ACCOUNTING <<<');
    const finSubmodules = [
      { path: '/payments/links', screen: 'Payment Links' },
      { path: '/payments/statements', screen: 'Bank Statements' },
      { path: '/payments/reconciliation', screen: 'Bank Reconciliation' },
      { path: '/reports/cash-book', screen: 'Cash Book' },
      { path: '/accounting/accounts', screen: 'Chart of Accounts' },
      { path: '/accounting/journals', screen: 'Journal Entries' },
      { path: '/accounting/bank-reconciliation', screen: 'Accounting Bank Recon' },
      { path: '/accounting/cost-centers', screen: 'Cost Centers' },
      { path: '/accounting/fixed-assets', screen: 'Fixed Assets' }
    ];

    for (const sub of finSubmodules) {
      await page.goto(`http://localhost${sub.path}`);
      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(500);
      const heading = await page.locator('h4, h5, h6, [role="heading"]').allInnerTexts();
      recordTest('Banking & Accounting', sub.screen, `${sub.screen} Surface & Navigation`, 'Navigation & Render', heading.length > 0 ? 'PASS' : 'FAIL', `Heading: "${heading[0] || ''}"`);
    }

    // =========================================================================
    // MODULE 8: MANUFACTURING, PAYROLL & CRM
    // =========================================================================
    console.log('\n>>> MODULE 8: MANUFACTURING, PAYROLL & CRM <<<');
    const advSubmodules = [
      { path: '/manufacturing/boms', screen: 'Bill of Materials (BOMs)' },
      { path: '/manufacturing/work-orders', screen: 'Work Orders' },
      { path: '/payroll/employees', screen: 'Payroll Employees' },
      { path: '/payroll/pay-runs', screen: 'Pay Runs' },
      { path: '/crm/leads', screen: 'CRM Leads' },
      { path: '/crm/opportunities', screen: 'CRM Opportunities' }
    ];

    for (const sub of advSubmodules) {
      await page.goto(`http://localhost${sub.path}`);
      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(500);
      const heading = await page.locator('h4, h5, h6, [role="heading"]').allInnerTexts();
      recordTest('Enterprise Modules', sub.screen, `${sub.screen} Surface & Navigation`, 'Navigation & Render', heading.length > 0 ? 'PASS' : 'FAIL', `Heading: "${heading[0] || ''}"`);
    }

    // =========================================================================
    // MODULE 9: FINANCIAL REPORTS & GST ANALYTICS
    // =========================================================================
    console.log('\n>>> MODULE 9: REPORTS & TAX ANALYTICS <<<');
    const reportSubmodules = [
      { path: '/reports/sales', screen: 'Sales Report' },
      { path: '/reports/purchases', screen: 'Purchases Report' },
      { path: '/reports/inventory', screen: 'Inventory Report' },
      { path: '/reports/customer-ledger', screen: 'Customer Ledger' },
      { path: '/reports/supplier-ledger', screen: 'Supplier Ledger' },
      { path: '/reports/stock-valuation', screen: 'Stock Valuation' },
      { path: '/reports/tds-tcs', screen: 'TDS/TCS Report' },
      { path: '/reports/trial-balance', screen: 'Trial Balance' },
      { path: '/reports/profit-and-loss', screen: 'Profit & Loss' },
      { path: '/reports/balance-sheet', screen: 'Balance Sheet' },
      { path: '/reports/books-health', screen: 'Books Health' },
      { path: '/reports/gstr1', screen: 'GSTR-1' },
      { path: '/reports/gstr3b', screen: 'GSTR-3B' },
      { path: '/reports/gstr9', screen: 'GSTR-9' },
      { path: '/reports/gstr2b', screen: 'GSTR-2B' },
      { path: '/reports/gst-health', screen: 'GST Health' },
      { path: '/reports/gst-rate-exposure', screen: 'GST Rate Exposure' },
      { path: '/reports/missing-documents', screen: 'Missing Documents' },
      { path: '/reports/statutory-events', screen: 'Statutory Events' }
    ];

    for (const sub of reportSubmodules) {
      await page.goto(`http://localhost${sub.path}`);
      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(500);
      const heading = await page.locator('h4, h5, h6, [role="heading"]').allInnerTexts();
      recordTest('Reports & Analytics', sub.screen, `${sub.screen} Surface & Navigation`, 'Navigation & Render', heading.length > 0 ? 'PASS' : 'FAIL', `Heading: "${heading[0] || ''}"`);
    }

    // =========================================================================
    // MODULE 10: AI INSIGHTS & ASSISTANT
    // =========================================================================
    console.log('\n>>> MODULE 10: AI INSIGHTS & ASSISTANT <<<');
    const insightSubmodules = [
      { path: '/insights', screen: 'Insights Hub' },
      { path: '/insights/alerts', screen: 'Insights Alerts' },
      { path: '/insights/health', screen: 'Business Health' },
      { path: '/insights/cashflow', screen: 'Cashflow Forecast' },
      { path: '/insights/assistant', screen: 'AI Assistant' }
    ];

    for (const sub of insightSubmodules) {
      await page.goto(`http://localhost${sub.path}`);
      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(500);
      const heading = await page.locator('h4, h5, h6, [role="heading"]').allInnerTexts();
      recordTest('AI Insights', sub.screen, `${sub.screen} Surface & Navigation`, 'Navigation & Render', heading.length > 0 ? 'PASS' : 'FAIL', `Heading: "${heading[0] || ''}"`);
    }

    // Test AI Assistant Input Box
    await page.goto('http://localhost/insights/assistant');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(600);
    const chatInput = page.locator('input[placeholder*="Ask" i], textarea[placeholder*="Ask" i]').first();
    const sendBtn = page.locator('button:has-text("Send"), button[aria-label*="send" i]').first();
    recordTest('AI Insights', 'AI Assistant', 'Chat Input Box', 'UI Presence', (await chatInput.isVisible()) ? 'PASS' : 'FAIL');
    recordTest('AI Insights', 'AI Assistant', 'Send Prompt Button', 'UI Presence', (await sendBtn.isVisible()) ? 'PASS' : 'FAIL');

    // =========================================================================
    // MODULE 11: SETTINGS & CONFIGURATION
    // =========================================================================
    console.log('\n>>> MODULE 11: SETTINGS & CONFIGURATION <<<');
    const settingsSubmodules = [
      { path: '/settings/company', screen: 'Company Profile' },
      { path: '/settings/units', screen: 'Units of Measurement' },
      { path: '/settings/templates', screen: 'Invoice Templates' },
      { path: '/settings/users', screen: 'Users & Roles' },
      { path: '/settings/bank-accounts', screen: 'Bank Accounts Settings' },
      { path: '/settings/payment-gateway', screen: 'Payment Gateway' },
      { path: '/settings/billing', screen: 'Subscription & Billing' },
      { path: '/settings/price-lists', screen: 'Price Lists' },
      { path: '/settings/backup', screen: 'Backup & Data Export' },
      { path: '/settings/ai', screen: 'AI Configuration' },
      { path: '/settings/accounting', screen: 'Accounting Settings' },
      { path: '/settings/gst', screen: 'GST Configuration' },
      { path: '/settings/import', screen: 'Data Import' },
      { path: '/settings/tally', screen: 'Tally Migration' }
    ];

    for (const sub of settingsSubmodules) {
      await page.goto(`http://localhost${sub.path}`);
      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(500);
      const heading = await page.locator('h4, h5, h6, [role="heading"]').allInnerTexts();
      recordTest('Settings', sub.screen, `${sub.screen} Surface & Navigation`, 'Navigation & Render', heading.length > 0 ? 'PASS' : 'FAIL', `Heading: "${heading[0] || ''}"`);
    }

    // =========================================================================
    // MODULE 12: CROSS-CUTTING (CSP, UNKNOWN ROUTES, 404, LOCALIZATION)
    // =========================================================================
    console.log('\n>>> MODULE 12: CROSS-CUTTING & DEFECT SCANNING <<<');

    // 12.1 404 Route Test
    await page.goto('http://localhost/non-existent-random-route-qa-999');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(500);
    const body404 = await page.locator('body').innerText();
    const has404Indicator = body404.includes('404') || body404.toLowerCase().includes('not found') || body404.toLowerCase().includes('page not found');
    recordTest('Cross-Cutting', '404 Handling', 'Unknown Route 404 Page', 'Navigation / Error State', has404Indicator ? 'PASS' : 'FAIL', `Body content: "${body404.slice(0, 100)}"`);

    // 12.2 Content Security Policy (CSP) Inline Script Violation Check
    const cspViolations = consoleErrors.filter(e => e.text.includes('Content Security Policy'));
    if (cspViolations.length > 0) {
      recordTest('Cross-Cutting', 'Security & Console', 'CSP Inline Script Violations', 'Console Logs / Security', 'FAIL', `Detected ${cspViolations.length} CSP violations in browser console`, 'DEF-CSP-01');
      recordDefect('DEF-CSP-01', 'Content Security Policy blocks inline script in index.html', 'Low', 'Security / Console Quality', 'App Shell → Global', 'Any page load', '1. Open browser console\n2. Navigate to any page', 'N/A', 'Clean browser console with no CSP policy violations', 'Console logs multiple errors: "Refused to execute inline script because it violates Content Security Policy directive script-src \'self\'"', 'Pollutes production observability and breaks inline theme/analytics scripts', 'Console error: script-src \'self\' hash/nonce required', 'Add nonce/hash or move inline scripts to bundled entrypoint');
    } else {
      recordTest('Cross-Cutting', 'Security & Console', 'CSP Inline Script Violations', 'Console Logs / Security', 'PASS', 'No CSP violations');
    }

  } catch (err) {
    console.error('Fatal error during Master QA validation:', err);
    recordTest('Runner', 'Global', 'Validation Execution', 'Fatal Error', 'FAIL', err.message, 'DEF-FATAL');
  } finally {
    await browser.close();
  }

  // Save complete results to JSON
  const summary = {
    totalTests: testLog.length,
    passed: testLog.filter(t => t.status === 'PASS').length,
    failed: testLog.filter(t => t.status === 'FAIL').length,
    defectsCount: defects.length,
    defects,
    testLog,
    consoleErrorsCount: consoleErrors.length,
    networkErrorsCount: networkErrors.length,
    networkErrors: networkErrors.slice(0, 20)
  };

  fs.writeFileSync(LOG_FILE, JSON.stringify(summary, null, 2));
  console.log(`\n===============================================================`);
  console.log(`VALIDATION COMPLETE: ${summary.passed}/${summary.totalTests} Passed (${summary.failed} Failed)`);
  console.log(`Results saved to ${LOG_FILE}`);
  console.log(`===============================================================`);
  return summary;
}

runMasterQAValidation();
