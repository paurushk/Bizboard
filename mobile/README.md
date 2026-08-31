# Bizboard Mobile (Capacitor)

Installable **WebView shell** over the existing Bizboard web app (`web/`). This is **not** a rewritten native UI, **not** an App Store product, and **not** a full offline MES/HRMS/CRM client — it wraps the same React SPA built to `web/dist`.

Android Play **internal testing** is the supported distribution path. There is **no iOS App Store binary** in this repo.

## Prerequisites

1. Build the web app: from repo root, `cd web && npm run build`
2. Node.js 18+
3. Android Studio + Android SDK (API 34 / Capacitor 6 default) for local runs and Play uploads

## Setup

```bash
cd mobile
npm install
npx cap add android   # first time only if android/ is missing
# optional (macOS + Xcode only — not shipped):
# npx cap add ios
npx cap sync
npx cap open android
```

Exact Capacitor 6 commands used to generate the committed `android/` tree:

```bash
cd mobile
npm install
npx cap add android
npx cap sync android
```

If `cap add android` fails because the Android SDK is not installed, install Android Studio, accept SDK licenses, set `ANDROID_HOME`, then re-run the commands above. A minimal `mobile/android` scaffold may already be committed so Play internal testing can proceed after `cap sync`.

## Play internal testing

1. `cd web && npm run build`
2. `cd ../mobile && npx cap sync android`
3. Open Android Studio (`npx cap open android`) → Generate signed App Bundle / APK
4. Upload the AAB to Google Play Console → **Internal testing** track
5. Add testers by email / Google Group; they install via the Play internal-test link

This scaffold is a WebView wrapper, not a native feature rewrite.

## Secure cookie / WebView notes

- Production must be **HTTPS**. Do not enable cleartext HTTP traffic in release (`android:usesCleartextTraffic` must stay false for prod).
- Auth cookies need `Secure` + appropriate `SameSite` (`None` if the WebView origin differs from the API host; `Lax`/`Strict` if same-site).
- Capacitor’s `androidScheme: 'https'` serves the bundled SPA from an `https://` origin. Cross-origin API calls still require CORS + cookie `SameSite=None; Secure` if the API host is different.
- Avoid mixed content. Point `server.url` at a LAN backend only for local debug, never for Play builds.

## iOS (optional, not shipped)

```bash
npx cap add ios
npx cap sync ios
npx cap open ios
```

No App Store binary is produced or maintained here.

## Offline billing (A-01 / A-04 / C-01)

Target: a shop can bill for **8 hours** with no WAN. Drafts queue in IndexedDB (winner) and Capacitor Preferences (native mirror). Complete of queued sales when online is idempotent. If device storage is full, new lines are blocked (`pos.storageFull`) — unpaid drafts are never FIFO-evicted.

Lab check: queue at least **50** POS drafts on an emulator, restore network, confirm flush. Thermal print from tap to data on a local Bluetooth printer should be **< 2s**; if the PDF path cannot meet that, use the existing 80mm thermal renderer (follow-up, not claimed here).

This README does **not** claim the app is listed on Google Play.

## Notes

- `capacitor.config.ts` points `webDir` at `../web/dist` — rebuild web before `cap sync` when UI changes.
- Push: native shell registers a device token and PATCHes `/auth/me/` `{ pushToken }`. No new notification product.
- Outbox: IndexedDB wins when both IDB and Preferences have a copy. Web without Capacitor uses localStorage + IDB only.
