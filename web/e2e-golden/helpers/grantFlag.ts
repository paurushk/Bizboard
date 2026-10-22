import { execFile, execFileSync } from 'node:child_process';
import { promisify } from 'node:util';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const execFileAsync = promisify(execFile);

const backend = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../../backend');

/** Grant one rollout flag on the company that owns this email.

The golden API process does not export ENABLE_WORKSHOP, ENABLE_PROJECTS, or
ENABLE_INSURANCE. Those keys turn on from company JSON even when the process
default is off, and company PATCH leaves feature_flags read-only.
 */
function manage(args: string[], djangoEnv = 'development', timeout?: number) {
  if (process.env.E2E_GOLDEN_SKIP_WEBSERVER === '1') {
    execFileSync('docker', ['exec', '-i', 'bizboard-api-1', 'python', 'manage.py', ...args], {
      stdio: 'pipe',
    });
    return;
  }
  const python = process.env.E2E_PYTHON || 'python';
  execFileSync(python, ['manage.py', ...args], {
    cwd: backend,
    env: {
      ...process.env,
      E2E_GOLDEN_GRANT: '1',
      DJANGO_SETTINGS_MODULE: 'config.settings',
      DJANGO_DEBUG: '1',
      DJANGO_ENV: djangoEnv,
      OTP_PEPPER: process.env.OTP_PEPPER || 'e2e-otp-pepper-not-for-prod',
    },
    stdio: 'pipe',
    timeout,
  });
}

export function grantRolloutFlag(email: string, flag: string) {
  manage(['grant_rollout_flag', '--email', email, '--flag', flag]);
}

export function ensureE2eTrial(email: string) {
  manage(['ensure_e2e_trial', '--email', email]);
}

export function markE2eVendor(email: string) {
  manage(['mark_e2e_vendor', '--email', email]);
}

/** Add the demo manufacturing set-up (recipes, work centre, operator DEMO1 with PIN 2468) to this email's company. */
export function seedManufacturingDemo(email: string) {
  manage(['seed_manufacturing_demo', '--email', email]);
}

/**
 * QOS-0016: complete `invoices` sales invoices, spread over the last 360 days, in this company
 * through SalesService.complete (seed_load_tenant reuses an existing company and its owner).
 * That command runs only under DJANGO_ENV=test or staging. The work is split over `shards`
 * processes (seed_load_tenant --shard i/n) so a slow machine still finishes in minutes.
 */
export async function seedTwelveMonthsOfInvoices(companyName: string, password: string, invoices: number, shards = 4) {
  const args = ['seed_load_tenant', '--company', companyName, '--password', password,
    '--invoices', String(invoices), '--products', '40', '--customers', '25', '--span-days', '360'];
  // Masters (and invoice 0) once, before the shards share them; shard 0 skips invoice 0 later.
  manage([...args, '--invoices', '0'], 'test', 5 * 60_000);
  const python = process.env.E2E_PYTHON || 'python';
  const env = {
    ...process.env,
    E2E_GOLDEN_GRANT: '1',
    DJANGO_SETTINGS_MODULE: 'config.settings',
    DJANGO_DEBUG: '1',
    DJANGO_ENV: 'test',
    OTP_PEPPER: process.env.OTP_PEPPER || 'e2e-otp-pepper-not-for-prod',
  };
  await Promise.all(
    Array.from({ length: shards }, (_, i) =>
      execFileAsync(python, ['manage.py', ...args, '--shard', `${i}/${shards}`], { cwd: backend, env, timeout: 20 * 60_000 }),
    ),
  );
}
