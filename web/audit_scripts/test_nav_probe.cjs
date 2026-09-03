const { chromium } = require('@playwright/test');

(async () => {
  const b = await chromium.launch();
  const context = await b.newContext({
    serviceWorkers: 'block'
  });
  const p = await context.newPage();

  console.log('1. Going to login (with serviceWorkers blocked)...');
  await p.goto('http://localhost/login');
  await p.waitForLoadState('networkidle');
  await p.locator('input[type="email"]').fill('demo@bizboard.local');
  await p.locator('input[type="password"]').fill('DemoPass123!');
  await p.locator('button[type="submit"]').click();
  await p.waitForTimeout(2000);
  console.log('Post-login URL:', p.url());

  console.log('2. Going to /sales/customers...');
  await p.goto('http://localhost/sales/customers');
  await p.waitForLoadState('networkidle');
  await p.waitForTimeout(1500);
  console.log('Current URL on customers:', p.url());
  console.log('Headings on customers:', await p.locator('h1, h2, h3, h4, h5, h6').allInnerTexts());
  console.log('Buttons on customers:', await p.locator('button').allInnerTexts());

  console.log('3. Going to /settings/company...');
  await p.goto('http://localhost/settings/company');
  await p.waitForLoadState('networkidle');
  await p.waitForTimeout(1500);
  console.log('Current URL on company:', p.url());
  console.log('Headings on company:', await p.locator('h1, h2, h3, h4, h5, h6').allInnerTexts());
  console.log('Inputs on company:', await p.locator('input').count());

  await b.close();
})();
