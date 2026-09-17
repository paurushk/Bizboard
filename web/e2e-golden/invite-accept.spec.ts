import { expect, test } from '@playwright/test';
import {
  inviteStaffViaToken,
  registerTenant,
  signOut,
  unique,
} from './helpers/documents';

test('invite token: accept lands inside the tenant', async ({ page }) => {
  test.setTimeout(150_000);
  page.on('dialog', (dialog) => dialog.accept());
  const id = unique();
  const ownerEmail = `e2e-invite-owner-${id}@example.test`;
  const staffEmail = `e2e-invite-staff-${id}@example.test`;
  const password = 'GoldenPath123!';

  await registerTenant(page, {
    companyName: `E2E Invite ${id}`,
    email: ownerEmail,
    password,
    gstin: false,
  });
  const invite = await inviteStaffViaToken(page, {
    email: staffEmail,
    fullName: `Invited Staff ${id}`,
  });
  expect(invite.inviteUrl || invite.inviteToken, invite.raw).toBeTruthy();
  await signOut(page);

  if (invite.inviteUrl) {
    const path = invite.inviteUrl.startsWith('http')
      ? new URL(invite.inviteUrl).pathname + new URL(invite.inviteUrl).search
      : invite.inviteUrl;
    await page.goto(path.startsWith('/') ? path : `/invite?token=${invite.inviteToken}`);
  } else {
    await page.goto('/invite');
    await page.getByLabel('Invite token').fill(invite.inviteToken!);
  }
  await page.getByLabel('New password').fill(password);
  await page.getByRole('button', { name: 'Activate account' }).click();
  await expect(page.getByRole('navigation', { name: 'Main navigation' })).toBeVisible({
    timeout: 20_000,
  });
});
