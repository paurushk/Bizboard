# Final Gates for Production Readiness / Accounting / GST **10/10**

Wave 16 ships all **code** that can be built without live vendor credentials or
human signatures. The following remain **non-negotiable** before any scorecard,
marketing claim, or GO decision may say **10/10**.

| Gate | Owner | Evidence |
|------|-------|----------|
| Signed [`GO_NO_GO.md`](GO_NO_GO.md) | PM/Eng/QA/CA/Ops | All roles dated Go |
| TLS + HSTS on pilot/prod host | Ops | Certificate + edge config |
| Dated backup **restore drill** | Ops | Date + RPO/RTO in GO_NO_GO |
| Host digest verify each deploy | Ops | `pin_image_digests.sh` output checked on host |
| Sentry DSN + PagerDuty/on-call | Ops | Alert fires on staging test event |
| SMTP spot-send in prod | Ops | Test email received |
| SMS vendor + DLT (if OTP on) | Ops | Live MSG91/Twilio send |
| Live NIC/GSP credentials | Ops/Eng | `GSP_LIVE_ENABLED=1` + provider prod URL + company secrets |
| CA Tax Invoice letter + samples | CA | Stored with F9 checklist |

Until this list is empty, honest narrative scores stay at Wave 16 engineering ceiling
(~PR **8.5**, Accounting **9.0**, GST **8.5**).
