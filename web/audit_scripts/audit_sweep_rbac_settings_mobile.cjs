const { createAuditBrowser } = require('./helper.cjs');

async function runSweep3() {
  const audit = await createAuditBrowser();
  const { page, takeScreenshot, login } = audit;

  try {
    console.log('=== LOGGING IN FOR SWEEP 3: SETTINGS, RBAC & MOBILE ===');
    await login('demo@bizboard.local', 'DemoPass123!');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);

    const settingsRoutes = [
      { path: '/settings/company', name: 'UXW2-094_settings_company' },
      { path: '/settings/units', name: 'UXW2-095_settings_units' },
      { path: '/settings/templates', name: 'UXW2-096_settings_templates' },
      { path: '/settings/users', name: 'UXW2-097_settings_users' },
      { path: '/settings/bank-accounts', name: 'UXW2-098_settings_bank_accounts' },
      { path: '/settings/payment-gateway', name: 'UXW2-099_settings_payment_gateway' },
      { path: '/settings/billing', name: 'UXW2-100_settings_billing' },
      { path: '/settings/price-lists', name: 'UXW2-101_settings_price_lists' },
      { path: '/settings/backup', name: 'UXW2-102_settings_backup' },
      { path: '/settings/ai', name: 'UXW2-103_settings_ai' },
      { path: '/settings/accounting', name: 'UXW2-104_settings_accounting' },
      { path: '/settings/gst', name: 'UXW2-105_settings_gst' },
      { path: '/settings/import', name: 'UXW2-106_settings_import' },
      { path: '/settings/tally', name: 'UXW2-107_settings_tally' },
    ];

    for (const r of settingsRoutes) {
      console.log(`Navigating to ${r.path}...`);
      await page.goto(`http://localhost${r.path}`);
      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(800);
      await takeScreenshot(r.name);
    }

    // -------------------------------------------------------------
    // RBAC: CREATE / INVITE STAFF USER & TEST RESTRICTIONS
    // -------------------------------------------------------------
    console.log('=== RBAC: TESTING USER MANAGEMENT & ROLES ===');
    await page.goto('http://localhost/settings/users');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);

    // Invite user modal
    const inviteBtn = page.locator('button:has-text("Invite"), button:has-text("Add"), button:has-text("New")').first();
    if (await inviteBtn.isVisible()) {
      await inviteBtn.click();
      await page.waitForTimeout(800);
      await takeScreenshot('UXW2-108_invite_user_modal');

      const emailInput = page.locator('div[role="dialog"] label:has-text("Email")').locator('..').locator('input').first();
      if (await emailInput.isVisible()) {
        await emailInput.fill('uxwave2_staff@bizboard.local');
      }

      const roleSelect = page.locator('div[role="dialog"] label:has-text("Role")').locator('..').locator('div[role="combobox"], select, input').first();
      if (await roleSelect.isVisible()) {
        await roleSelect.click();
        await page.waitForTimeout(300);
        const staffOpt = page.locator('li:has-text("Staff"), li:has-text("Operator"), li:has-text("Sales")').first();
        if (await staffOpt.isVisible()) await staffOpt.click();
      }

      await takeScreenshot('UXW2-109_invite_user_form_filled');
      const sendInviteBtn = page.locator('div[role="dialog"] button:has-text("Invite"), div[role="dialog"] button:has-text("Save"), div[role="dialog"] button:has-text("Send")').first();
      if (await sendInviteBtn.isVisible()) {
        await sendInviteBtn.click();
        await page.waitForTimeout(1500);
      }
      await takeScreenshot('UXW2-110_users_list_after_invite');
    }

    // -------------------------------------------------------------
    // MOBILE VIEWPORT SWEEP (375 x 812)
    // -------------------------------------------------------------
    console.log('=== MOBILE VIEWPORT SWEEP (375 x 812) ===');
    await page.setViewportSize({ width: 375, height: 812 });
    await page.goto('http://localhost/');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-111_mobile_dashboard');

    // Open hamburger menu
    const menuBtn = page.locator('button[aria-label*="menu" i], button[aria-label*="navigation" i], header button').first();
    if (await menuBtn.isVisible()) {
      await menuBtn.click();
      await page.waitForTimeout(600);
      await takeScreenshot('UXW2-112_mobile_nav_drawer_open');
      // Close drawer by clicking backdrop
      await page.keyboard.press('Escape');
      await page.waitForTimeout(400);
    }

    // Mobile Sales Invoice
    await page.goto('http://localhost/sales/new');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-113_mobile_sales_invoice_form');

    // Mobile Inventory Stock Table
    await page.goto('http://localhost/inventory/stock');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-114_mobile_inventory_stock_table');

    // Mobile Settings
    await page.goto('http://localhost/settings/company');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-115_mobile_settings_company');

    // Mobile POS
    await page.goto('http://localhost/pos');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);
    await takeScreenshot('UXW2-116_mobile_pos_screen');

    console.log('=== SWEEP 3 COMPLETED SUCCESSFULLY ===');
  } catch (err) {
    console.error('Error during Sweep 3:', err);
    await takeScreenshot('UXW2-ERROR_sweep3');
  } finally {
    await audit.cleanup();
  }
}

runSweep3();
