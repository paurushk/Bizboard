# What's new in Bizboard

The in-app "What's new" panel shows these entries (English and Hindi). The text lives in
`web/src/help/whatsNew.ts`; this page lists the same entries for people reading the docs.
`guard_whats_new` (CI) fails when the two disagree or an entry has no Hindi text.

Add a new entry at the top of both, with an id that starts with today's date. Staff maintenance
or incident banners are not written here: add them in Django admin → Announcements.

## 2026-10-22-signed-in-devices — See and sign out your devices

Settings → Users lists the devices your account is signed in on; sign out any you do not
recognise. A sign-in from a new device sends you an email.

## 2026-10-22-tds-credit — TDS on Bizboard fees comes off your renewal

Claim back TDS deducted on Bizboard invoices under Billing. After the Form 16A check the amount
comes off the next renewal, or is refunded on request.

## 2026-10-22-support-access — Let support look without a screen share

An owner can let Bizboard support view the company data for one request, read-only, for up to
72 hours, from Help → Contact support. Every page support opens is listed for the owner.
