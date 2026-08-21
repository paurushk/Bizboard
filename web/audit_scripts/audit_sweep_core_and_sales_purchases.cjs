const { createAuditBrowser } = require('./helper.cjs');

async function runSweep1() {
  const audit = await createAuditBrowser();
  const { page, takeScreenshot, login } = audit;

  try {
    console.log('=== LOGGING IN FOR SWEEP 1: SALES & PURCHASES ===');
    await login('demo@bizboard.local', 'DemoPass123!');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);

    const routes = [
      { path: '/sales/quotations', name: 'UXW2-033_quotations_page' },
      { path: '/sales/orders', name: 'UXW2-034_sales_orders_page' },
      { path: '/sales/orders/new', name: 'UXW2-035_sales_order_new_page' },
      { path: '/sales/delivery-challans', name: 'UXW2-036_delivery_challans_page' },
      { path: '/sales/delivery-challans/new', name: 'UXW2-037_delivery_challan_new_page' },
      { path: '/sales/recurring', name: 'UXW2-038_recurring_invoices_page' },
      { path: '/sales/returns', name: 'UXW2-039_sales_returns_page' },
      { path: '/sales/credit-notes', name: 'UXW2-040_sales_credit_notes_page' },
      { path: '/sales/credit-notes/new', name: 'UXW2-041_sales_credit_note_new_page' },
      { path: '/sales/debit-notes', name: 'UXW2-042_sales_debit_notes_page' },
      { path: '/sales/debit-notes/new', name: 'UXW2-043_sales_debit_note_new_page' },
      { path: '/sales/receipts', name: 'UXW2-044_sales_receipts_page' },
      { path: '/pos', name: 'UXW2-045_pos_terminal_page' },
      { path: '/purchases/orders', name: 'UXW2-046_purchase_orders_page' },
      { path: '/purchases/orders/new', name: 'UXW2-047_purchase_order_new_page' },
      { path: '/purchases/history', name: 'UXW2-048_purchases_history_page' },
      { path: '/purchases/credit-notes', name: 'UXW2-049_purchase_credit_notes_page' },
      { path: '/purchases/credit-notes/new', name: 'UXW2-050_purchase_credit_note_new_page' },
      { path: '/purchases/debit-notes', name: 'UXW2-051_purchase_debit_notes_page' },
      { path: '/purchases/debit-notes/new', name: 'UXW2-052_purchase_debit_note_new_page' },
      { path: '/purchases/returns', name: 'UXW2-053_purchase_returns_page' },
      { path: '/purchases/bill-upload', name: 'UXW2-054_purchase_bill_upload_page' },
      { path: '/purchases/payments', name: 'UXW2-055_purchases_payments_page' },
    ];

    for (const r of routes) {
      console.log(`Navigating to ${r.path}...`);
      await page.goto(`http://localhost${r.path}`);
      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(800);
      await takeScreenshot(r.name);
    }

    console.log('=== SWEEP 1 COMPLETED SUCCESSFULLY ===');
  } catch (err) {
    console.error('Error during Sweep 1:', err);
    await takeScreenshot('UXW2-ERROR_sweep1');
  } finally {
    await audit.cleanup();
  }
}

runSweep1();
