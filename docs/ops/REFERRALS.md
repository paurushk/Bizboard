# Bizboard referrals (D-19, BB-139)

One Bizboard customer refers another business. Built 2026-10-25, **off for every company**.
Not the CRM referral codes (`ENABLE_REFERRALS`, a tenant's own customers).

## Turning it on for a company

In Django admin → Accounts → Companies → the company → **Feature flags** (JSON), add
`"ENABLE_SAAS_REFERRALS": true` and save (layer 3 in `docs/ops/FLAG_LIFECYCLE.md`). Remove the key, or set it
to false, to turn it off again. The owner then sees **Settings → Billing → Refer a business**
with their link (`/register?ref=<code>`), copy and WhatsApp-share buttons, and two counts. They
never see which businesses signed up.

## What gets recorded

| When | Recorded | Where |
|---|---|---|
| A business signs up with the link (password or Google) | SIGNED_UP event for the referrer | `billing.ReferralEvent` |
| That business is ACTIVE on a paid plan (daily job at 05:10, `billing.tasks.qualify_saas_referrals_task`) | QUALIFIED event | same |
| Its GSTIN later matches the referrer's | the SIGNED_UP event is voided ("Same business") | same |

Sign-ups that don't count (nothing is recorded; the sign-up itself always succeeds):
- unknown, inactive or switched-off codes;
- the same GSTIN as the referrer;
- an owner email on the referrer's own company domain (public mail domains such as gmail.com do not count against this);
- more than `SAAS_REFERRAL_DAILY_CAP` (default 20) sign-ups per link per day.

## Settling a reward (by hand)

The product gives no credit or discount. Agree the reward with the referrer, then go to Django
admin → Billing → Referral events, filter **kind = Started paying, voided = empty, settled =
empty**, select the rows and choose **Mark settled**. Add a note on the row for what was given. Use
**Void** for a referral that isn't real. A money credit would need a GST credit note and the CA's
view first (D-19 chose "recorded only").

## Switching one link off

Django admin → Billing → Referral links → untick **Is active**. The owner sees "This link has been
switched off".
