import { expect, test } from '@playwright/test';
import { enableAccounting, registerTenant, unique } from './helpers/documents';

test('recon chrome: operational match vs GL match, both UIs kept', async ({ page }) => {
  test.setTimeout(90_000);
  const id = unique();
  await registerTenant(page, {
    companyName: `E2E Recon ${id}`,
    email: `e2e-recon-${id}@example.test`,
    password: 'GoldenPath123!',
  });
  await enableAccounting(page);

  await page.goto('/payments/reconciliation');
  await expect(page.getByText(/Operational match/i).first()).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText(/Not the GL bank recon/i).first()).toBeVisible();

  await page.goto('/accounting/bank-reconciliation');
  await expect(page.getByText(/GL match/i).first()).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText(/Not the operational payments recon/i).first()).toBeVisible();
});
