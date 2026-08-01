# Pilot support SLA & on-call (P0-616)

| Item | Pilot default |
|------|----------------|
| Hours | Mon–Sat 09:00–21:00 IST |
| First response | ≤ 4 business hours |
| Critical money/tenancy | ≤ 2 hours acknowledgment |
| Channel | (fill) email / WhatsApp / phone |
| Primary on-call | (fill name) |
| Backup | (fill name) |

## Kill criteria (P0-617) — stop pilot if

- Critical money or tenancy bug open > 72 hours  
- CA withdraws tax/PDF sign-off  
- PDF success rate < 95% over 7 days  
- Confirmed PII exposure incident  

## Graduation to Phase 1

- ≥5 pilots complete weekly purchase→sale→pay→return with zero total mismatches for 2 weeks  
- Quiet gate met (no open Criticals; no new Critical since UAT)  
- Go SHA == UAT SHA (or re-smoke signed)  
- PM + Eng agree to start Credit Notes / GSTR work  

## Sign-off

PM: ________  Eng: ________  Date: ________
