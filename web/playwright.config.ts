import { defineConfig, devices } from '@playwright/test';

const webBase = process.env.E2E_BASE_URL || 'http://127.0.0.1:5173';

export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? 'github' : 'list',
  use: {
    baseURL: webBase,
    trace: 'on-first-retry',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: process.env.E2E_SKIP_WEBSERVER
    ? undefined
    : {
        // --mode e2e loads .env.e2e (VITE_USE_MOCKS=true) so smoke runs without API/LLM.
        command: 'npm run dev -- --mode e2e --host 127.0.0.1 --port 5173',
        url: webBase,
        reuseExistingServer: !process.env.CI,
        timeout: 120_000,
      },
});
