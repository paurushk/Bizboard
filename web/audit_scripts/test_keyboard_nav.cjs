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
  await page.waitForTimeout(1000);

  // Supplier Autocomplete using ArrowDown + Enter
  console.log('Selecting supplier with keyboard...');
  const suppInput = page.locator('input[placeholder*="Type 2+"]').first();
  await suppInput.focus();
  await suppInput.pressSequentially('Alpha', { delay: 100 });
  await page.waitForTimeout(800);
  await page.keyboard.press('ArrowDown');
  await page.keyboard.press('Enter');
  await page.waitForTimeout(800);

  console.log('Party Box text:\n', await page.locator('text=Bill from').first().locator('..').innerText());

  // Product Autocomplete using ArrowDown + Enter
  console.log('Selecting product with keyboard...');
  const prodInput = page.locator('input[placeholder*="Scan barcode"], input[placeholder*="search SKU"]').first();
  await prodInput.focus();
  await prodInput.pressSequentially('Widget', { delay: 100 });
  await page.waitForTimeout(800);
  await page.keyboard.press('ArrowDown');
  await page.keyboard.press('Enter');
  await page.waitForTimeout(800);

  // Change Quantity to 20
  const qtyField = page.locator('table tbody tr td').locator('input').nth(1);
  if (await qtyField.isVisible()) {
    await qtyField.fill('20');
    await page.keyboard.press('Tab');
  }
  await page.waitForTimeout(800);

  const saveBtn = page.locator('button:has-text("Save & Complete")').first();
  console.log('Save & Complete disabled:', await saveBtn.isDisabled());

  if (!await saveBtn.isDisabled()) {
    console.log('Clicking Save & Complete...');
    await saveBtn.click();
    await page.waitForTimeout(2500);
    console.log('Purchase saved! URL is:', page.url());
  }

  await browser.close();
})();
