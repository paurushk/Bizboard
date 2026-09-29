import { execFileSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const backend = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../../backend');

/** Grant one rollout flag on the company that owns this email.

The golden API process does not export ENABLE_WORKSHOP, ENABLE_PROJECTS, or
ENABLE_INSURANCE. Those keys turn on from company JSON even when the process
default is off, and company PATCH leaves feature_flags read-only.
 */
function manage(args: string[]) {
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
      DJANGO_ENV: 'development',
      OTP_PEPPER: process.env.OTP_PEPPER || 'e2e-otp-pepper-not-for-prod',
    },
    stdio: 'pipe',
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
