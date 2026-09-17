# Email DNS (SPF / DKIM / DMARC) (10.10)

Operator publishes DNS. Product only sends through Django `EMAIL_*`.

## Suggested records (placeholders)

```
TXT  @          "v=spf1 include:your-smtp-include -all"
TXT  mail._domainkey   (DKIM public key from the SMTP vendor)
TXT  _dmarc     "v=DMARC1; p=quarantine; rua=mailto:dmarc@yourdomain"
```

## Verify

1. `python manage.py sendtestemail you@company` with real `EMAIL_HOST` set.
2. Paste the Message-ID into `docs/pilot/ENV_CHECKLIST.md` row 11. Do not tick the box on a claim.

Password-reset and invite mail use `DEFAULT_FROM_EMAIL`. Align From-domain with SPF.
