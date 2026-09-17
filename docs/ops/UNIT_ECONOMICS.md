# Unit economics draft (2.6)

**Draft numbers — not prices.** Founder sets INR list price vs SMS / PG / Razorpay burn.

Assumptions: freeze surface only (A1–A26). No GSTR filing, no WhatsApp Cloud, sandbox collections.

| Scale | Tenants | Completes / month | Infra (USD/mo, order of) | Variable | Notes |
|---|---|---|---|---|---|
| 10 | 10 | ~3k | 40–80 (1 VM + managed PG small) | SMS OTP + Razorpay fee | Pilot |
| 1k | 1k | ~300k | 400–800 (PG + Redis + 2 workers) | same | Needs pooling / k6 soak |
| 10k | 10k | ~3M | 4k–8k | same | Not freeze-sized (C7) |

SaaS list price must cover infra + GST on SaaS (CA — Human) + support. Do not enable Table B to raise ARPU during freeze.
