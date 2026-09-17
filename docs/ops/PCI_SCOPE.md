# PCI scope note (8.9)

Factual product posture. Not an SAQ, QSA letter, or counsel opinion.

## Card data

Online collection uses hosted Razorpay / Cashfree / PayU checkout. The
application stores **payment tokens / gateway ids / amounts**, not PAN, CVV,
or track data. `payments/services.py` lists inbound keys that must never be
persisted (`card_number`, `cvv`, …).

SaaS subscription billing is Razorpay Subscriptions; the same rule applies.

## What operators still own

- Razorpay / Cashfree / PayU merchant KYC and SAQ-A (if applicable)
- GST on SaaS invoices (CA)
- TLS at the edge so checkout pages are HTTPS

Do not paste live card numbers into tickets, logs, or this repo.
