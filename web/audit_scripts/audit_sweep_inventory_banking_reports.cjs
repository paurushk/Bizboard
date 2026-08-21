const { createAuditBrowser } = require('./helper.cjs');

async function runSweep2() {
  const audit = await createAuditBrowser();
  const { page, takeScreenshot, login } = audit;

  try {
    console.log('=== LOGGING IN FOR SWEEP 2: INVENTORY, BANKING & REPORTS ===');
    await login('demo@bizboard.local', 'DemoPass123!');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);

    const routes = [
      // Inventory
      { path: '/inventory/products', name: 'UXW2-056_inventory_products' },
      { path: '/inventory/stock', name: 'UXW2-057_inventory_stock' },
      { path: '/inventory/low-stock', name: 'UXW2-058_inventory_low_stock' },
      { path: '/inventory/expiry-alerts', name: 'UXW2-059_inventory_expiry_alerts' },
      { path: '/inventory/adjustments', name: 'UXW2-060_inventory_adjustments' },
      { path: '/inventory/warehouses', name: 'UXW2-061_inventory_warehouses' },
      { path: '/inventory/transfers', name: 'UXW2-062_inventory_transfers' },
      { path: '/inventory/serials', name: 'UXW2-063_inventory_serials' },

      // Banking & Payments
      { path: '/payments/links', name: 'UXW2-064_payments_links' },
      { path: '/payments/statements', name: 'UXW2-065_payments_statements' },
      { path: '/payments/reconciliation', name: 'UXW2-066_payments_reconciliation' },
      { path: '/reports/cash-book', name: 'UXW2-067_reports_cash_book' },

      // Standard Reports
      { path: '/reports/sales', name: 'UXW2-068_reports_sales' },
      { path: '/reports/purchases', name: 'UXW2-069_reports_purchases' },
      { path: '/reports/inventory', name: 'UXW2-070_reports_inventory' },
      { path: '/reports/customer-ledger', name: 'UXW2-071_reports_customer_ledger' },
      { path: '/reports/supplier-ledger', name: 'UXW2-072_reports_supplier_ledger' },
      { path: '/reports/statutory-events', name: 'UXW2-073_reports_statutory_events' },
      { path: '/reports/stock-valuation', name: 'UXW2-074_reports_stock_valuation' },
      { path: '/reports/tds-tcs', name: 'UXW2-075_reports_tds_tcs' },

      // GST Reports
      { path: '/reports/gstr1', name: 'UXW2-076_reports_gstr1' },
      { path: '/reports/gstr3b', name: 'UXW2-077_reports_gstr3b' },
      { path: '/reports/gstr9', name: 'UXW2-078_reports_gstr9' },
      { path: '/reports/gstr2b', name: 'UXW2-079_reports_gstr2b' },
      { path: '/reports/gst-health', name: 'UXW2-080_reports_gst_health' },

      // Financial Statements & Health
      { path: '/reports/trial-balance', name: 'UXW2-081_reports_trial_balance' },
      { path: '/reports/profit-and-loss', name: 'UXW2-082_reports_profit_and_loss' },
      { path: '/reports/balance-sheet', name: 'UXW2-083_reports_balance_sheet' },
      { path: '/reports/books-health', name: 'UXW2-084_reports_books_health' },

      // Accounting Core
      { path: '/accounting/accounts', name: 'UXW2-085_accounting_chart_of_accounts' },
      { path: '/accounting/journals', name: 'UXW2-086_accounting_journals' },
      { path: '/accounting/bank-reconciliation', name: 'UXW2-087_accounting_bank_reconciliation' },
      { path: '/accounting/cost-centers', name: 'UXW2-088_accounting_cost_centers' },
      { path: '/accounting/fixed-assets', name: 'UXW2-089_accounting_fixed_assets' },

      // Insights & AI
      { path: '/insights/alerts', name: 'UXW2-090_insights_alerts' },
      { path: '/insights/health', name: 'UXW2-091_insights_health' },
      { path: '/insights/cashflow', name: 'UXW2-092_insights_cashflow' },
      { path: '/insights/assistant', name: 'UXW2-093_insights_assistant' },
    ];

    for (const r of routes) {
      console.log(`Navigating to ${r.path}...`);
      await page.goto(`http://localhost${r.path}`);
      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(800);
      await takeScreenshot(r.name);
    }

    console.log('=== SWEEP 2 COMPLETED SUCCESSFULLY ===');
  } catch (err) {
    console.error('Error during Sweep 2:', err);
    await takeScreenshot('UXW2-ERROR_sweep2');
  } finally {
    await audit.cleanup();
  }
}

runSweep2();
