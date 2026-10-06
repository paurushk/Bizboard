// Throwaway: the project's golden config, launching the Chrome installed on this machine because the
// Playwright-managed browser build matching @playwright/test is not downloaded here.
import { defineConfig, devices } from '@playwright/test';
import base from './playwright.golden.config';

export default defineConfig({
  ...base,
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'], channel: 'chrome' } }],
});
