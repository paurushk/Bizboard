# Mobile Review

## Wave 22 (2026-08-06)

allowBackup true (746); no CI Android assemble (748); PWA API cache affects WebView (738).

## Wave 21 (2026-08-05)

Price lists bypassed on non-web clients (BB-000657). Company header race affects mobile (BB-000658).

## Wave 20 (2026-08-05)

POS/mobile prepaid return blocked by BB-000648.

## Wave 19 missed (2026-08-05)

No new mobile IDs; CSP (BB-000605) also breaks installed PWA/WebView.

## Wave 19 (2026-08-05)

Capacitor tree is config-only (BB-000575). PWA manifest without service worker (BB-000580). Do not claim Mobile App.


**Date:** 2026-08-02 · **Score: 2.5 / 10**

## Reality

- Responsive web drawer only.
- No native iOS/Android app.
- OTP path intended for mobile login is **not production-capable** (SMS stub).
- No offline outbox for counter billing on poor networks.
- Bundle/list performance concerns on mobile data (fetch-all).

## Issues

| Topic | Register |
|-------|----------|
| No native mobile | EXTRA / BB mobile |
| No offline mode | EXTRA |
| OTP SMS missing | BB-000006 |
| JWT localStorage on mobile browsers | BB-000031 |
| Large lists | BB-000034 |

## Recommendations

1. PWA installability + offline draft outbox before “mobile app” claims.
2. Or ship React Native against same API after OTP/SMS real.
3. Do not market “Mobile App” until one of the above ships.

## Score: 2.5 / 10


## Wave 8 (2026-08-03)

Still responsive-web only (BB-000179). Drawer UX bug BB-000242. No PWA.

---

## Wave 9 re-audit (2026-08-03)

Independent re-verification appended `BB-000258`…`BB-000317` (60 issues). See MASTER_ISSUE_REGISTER.md and CHANGELOG.md. Open count: **75**. Wave 6 Open==0 invalidated.

---

## Wave 12 re-audit (2026-08-03)

Independent re-verification appended `BB-000318`…`BB-000378` (61 issues). See MASTER_ISSUE_REGISTER.md and CHANGELOG.md. Open count was **61**; **Open: 0** after Wave 12 open-closure (2026-08-04). Waves 10–11 Open==0 invalidated historically.

---

## Wave 13 re-audit (2026-08-04)

Independent re-verification appended `BB-000379`…`BB-000455` (77 issues). See MASTER_ISSUE_REGISTER.md and CHANGELOG.md. Open count: **77**. Wave 12 Open==0 invalidated. Production Readiness **3.2 / 10**.

---

## Wave 14 re-audit (2026-08-04)

Independent re-verification appended `BB-000456`…`BB-000543` (88 issues). See MASTER_ISSUE_REGISTER.md and CHANGELOG.md. Open count: **88**. Wave 13 Open==0 invalidated. Production Readiness **3.4 / 10**.
