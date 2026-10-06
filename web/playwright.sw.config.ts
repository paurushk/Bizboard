import { defineConfig, devices } from '@playwright/test';

/**
 * Production-build worker check. Not part of `npm run test:e2e`
 * (that job runs Vite dev on 5173 and does not register this worker).
 * Build first: `npm run build`, then `npx playwright test -c playwright.sw.config.ts`.
 */
export default defineConfig({
  testDir: './e2e-sw',
  timeout: 60_000,
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  reporter: process.env.CI ? 'github' : 'list',
  use: {
    baseURL: 'http://127.0.0.1:4173',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: 'npm run preview -- --host 127.0.0.1 --port 4173 --strictPort',
    url: 'http://127.0.0.1:4173',
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
