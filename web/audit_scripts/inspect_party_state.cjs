const { chromium } = require('@playwright/test');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  await page.goto('http://localhost/login');
  await page.fill('input[type=email]', 'demo@bizboard.local');
  await page.fill('input[type=password]', 'DemoPass123!');
  await page.click('button[type=submit]');
  await page.waitForLoadState('networkidle');

  await page.goto('http://localhost/purchases/new');
  await page.waitForLoadState('networkidle');

  const suppInput = page.locator('input[placeholder*="Type 2+"]').first();
  await suppInput.focus();
  await suppInput.pressSequentially('UXWAVE2', { delay: 100 });
  await page.waitForTimeout(1000);
  await page.locator('li[role="option"]').first().click();
  await page.waitForTimeout(1000);

  const prodInput = page.locator('input[placeholder*="Scan barcode"], input[placeholder*="search SKU"]').first();
  await prodInput.focus();
  await prodInput.pressSequentially('UXWAVE2', { delay: 100 });
  await page.waitForTimeout(1000);
  await page.locator('li[role="option"]').first().click();
  await page.waitForTimeout(1000);

  // Inspect React component state / DOM / Tooltip
  const tooltipText = await page.locator('button:has-text("Save & Complete")').locator('..').getAttribute('aria-label') || await page.locator('button:has-text("Save & Complete")').locator('..').getAttribute('title');
  console.log('Tooltip text:', tooltipText);

  // Check what supplier is loaded
  const partyBox = await page.locator('text=Bill from').locator('..').innerText();
  console.log('Party Box text:\n', partyBox);

  // Check if warning alert or something is showing
  const alerts = await page.locator('div[role="alert"]').allInnerTexts();
  console.log('Alerts on page:', alerts);

  await browser.close();
})();
