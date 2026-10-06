import { defineConfig, devices } from '@playwright/test';

/** UX programme crawl config: uses the locally installed Chrome (no browser download). */
export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  reporter: 'list',
  use: { baseURL: process.env.E2E_BASE_URL || 'http://127.0.0.1:34521', channel: 'chrome' },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'], channel: 'chrome' } },
    { name: 'mobile', use: { ...devices['Pixel 5'], channel: 'chrome' } },
  ],
});
