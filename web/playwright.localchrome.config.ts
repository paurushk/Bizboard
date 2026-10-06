// Throwaway: the project's own config, but launching the Chrome installed on this machine because the
// Playwright-managed browser build that matches the installed @playwright/test is not downloaded here.
import { defineConfig, devices } from '@playwright/test';
import base from './playwright.config';

export default defineConfig({
  ...base,
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'], channel: 'chrome' } },
    { name: 'mobile', use: { ...devices['Pixel 5'], channel: 'chrome' } },
  ],
});
