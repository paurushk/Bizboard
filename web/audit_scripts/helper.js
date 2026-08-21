const { chromium } = require('@playwright/test');
const path = require('path');
const fs = require('fs');

const SCREENSHOT_DIR = path.resolve(__dirname, '../../docs/reviews/screenshots_wave2');

if (!fs.existsSync(SCREENSHOT_DIR)) {
  fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
}

async function createAuditBrowser(options = {}) {
  const isMobile = options.isMobile || false;
  const viewport = isMobile ? { width: 375, height: 812 } : { width: 1280, height: 800 };

  const browser = await chromium.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });

  const context = await browser.newContext({
    viewport,
    isMobile: isMobile,
    hasTouch: isMobile,
    deviceScaleFactor: 1,
  });

  const page = await context.newPage();

  const consoleLogs = [];
  const networkErrors = [];

  page.on('console', (msg) => {
    const text = msg.text();
    const type = msg.type();
    consoleLogs.push({ type, text, location: msg.location() });
    if (type === 'error') {
      console.log(`[BROWSER CONSOLE ERROR] ${text}`);
    }
  });

  page.on('pageerror', (err) => {
    consoleLogs.push({ type: 'pageerror', text: err.message, stack: err.stack });
    console.log(`[BROWSER UNCAUGHT ERROR] ${err.message}`);
  });

  page.on('response', (res) => {
    if (res.status() >= 400) {
      const url = res.url();
      const status = res.status();
      networkErrors.push({ url, status, statusText: res.statusText() });
      console.log(`[NETWORK ${status}] ${url}`);
    }
  });

  async function takeScreenshot(name) {
    const filename = `${name}.png`;
    const fullPath = path.join(SCREENSHOT_DIR, filename);
    await page.screenshot({ path: fullPath, fullPage: true });
    console.log(`Screenshot saved: ${filename}`);
    return filename;
  }

  async function login(email = 'demo@bizboard.local', password = 'DemoPass123!') {
    console.log(`Logging in as ${email}...`);
    await page.goto('http://localhost/login');
    await page.waitForLoadState('networkidle');

    // Check if redirected or on login page
    if (page.url().includes('/login')) {
      await page.fill('input[name="email"], input[type="email"], #email', email);
      await page.fill('input[name="password"], input[type="password"], #password', password);
      await page.click('button[type="submit"]');
      await page.waitForNavigation({ timeout: 10000 }).catch(() => {});
      await page.waitForTimeout(1500);
    }
    console.log(`Current URL after login: ${page.url()}`);
  }

  return {
    browser,
    context,
    page,
    consoleLogs,
    networkErrors,
    takeScreenshot,
    login,
    cleanup: async () => {
      await browser.close();
    }
  };
}

module.exports = {
  createAuditBrowser,
  SCREENSHOT_DIR
};
