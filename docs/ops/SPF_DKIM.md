# Email DNS (SPF / DKIM / DMARC) (10.10)

Operator publishes DNS. Product only sends through Django `EMAIL_*`.

## Vendor: Resend (SMTP relay)

1. In the Resend dashboard, add the sending domain (the one in
   `DEFAULT_FROM_EMAIL`) under Domains, then copy the exact SPF/DKIM records
   it generates — they're per-domain (unique DKIM selector), so don't reuse
   another domain's values or the placeholders below.
2. Set `EMAIL_HOST=smtp.resend.com`, `EMAIL_PORT=587`,
   `EMAIL_HOST_USER=resend`, `EMAIL_HOST_PASSWORD=<Resend API key>`.
3. Wait for the domain to show "Verified" in the Resend dashboard before
   sending — unverified domains are rejected or land in spam.

## Suggested records (placeholders — use Resend's generated values instead when live)

```
TXT  @          "v=spf1 include:your-smtp-include -all"
TXT  mail._domainkey   (DKIM public key from the SMTP vendor)
TXT  _dmarc     "v=DMARC1; p=quarantine; rua=mailto:dmarc@yourdomain"
```

## Verify

1. `python manage.py sendtestemail you@company` with real `EMAIL_HOST` set.
2. Paste the Message-ID into `docs/pilot/ENV_CHECKLIST.md` row 11. Do not tick the box on a claim.

Password-reset and invite mail use `DEFAULT_FROM_EMAIL`. Align From-domain with SPF.
