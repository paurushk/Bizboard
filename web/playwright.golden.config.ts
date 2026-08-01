import { defineConfig, devices } from '@playwright/test';

/**
 * BUG-725 — a real end-to-end run against the live backend (no mocks),
 * covering the golden path: register -> create product/customer -> invoice
 * -> complete -> stock decrement -> receipt -> allocate -> PDF download.
 *
 * Prerequisites (not automated here, matches any other real-backend run):
 *   cd backend && python manage.py migrate
 *
 * Run with: npm run test:e2e:golden
 * Override ports (e.g. if 8000/5173 are already in use locally) with
 * E2E_GOLDEN_API_PORT / E2E_GOLDEN_WEB_PORT.
 */
const apiPort = process.env.E2E_GOLDEN_API_PORT || '8000';
const webPort = process.env.E2E_GOLDEN_WEB_PORT || '5173';
const backendBase = process.env.E2E_GOLDEN_API_URL || `http://127.0.0.1:${apiPort}`;
const webBase = process.env.E2E_GOLDEN_BASE_URL || `http://127.0.0.1:${webPort}`;

export default defineConfig({
  testDir: './e2e-golden',
  timeout: 60_000,
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: 0,
  reporter: process.env.CI ? 'github' : 'list',
  use: {
    baseURL: webBase,
    trace: 'on-first-retry',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: process.env.E2E_GOLDEN_SKIP_WEBSERVER
    ? undefined
    : [
        {
          command: `python manage.py runserver 127.0.0.1:${apiPort} --noreload`,
          cwd: '../backend',
          url: `${backendBase}/api/v1/health/`,
          reuseExistingServer: !process.env.CI,
          timeout: 60_000,
          env: {
            // No Redis broker in this test environment (or CI) — run Celery
            // tasks (PDF generation) in-process so Complete never blocks on
            // a broker connection that isn't there.
            CELERY_TASK_ALWAYS_EAGER: '1',
          },
        },
        {
          command: `npm run dev -- --host 127.0.0.1 --port ${webPort}`,
          cwd: '.',
          url: webBase,
          reuseExistingServer: !process.env.CI,
          timeout: 60_000,
          env: {
            VITE_API_PROXY_TARGET: backendBase,
          },
        },
      ],
});
