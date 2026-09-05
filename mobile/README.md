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

### Command-line release build (M1-017)

The signed `bundleRelease` path (CI or any non-Android-Studio build):

```bash
cd web && npm run build
cd ../mobile && npx cap sync android
cd android && ./gradlew :app:bundleRelease -x lint \
  -PbizboardVersionCode=$(git rev-list --count HEAD) \
  -PbizboardVersionName=1.0
```

Signing is picked up from environment variables (or `-P` properties):
`BIZBOARD_KEYSTORE_FILE`, `BIZBOARD_KEYSTORE_PASSWORD`, `BIZBOARD_KEY_ALIAS`,
`BIZBOARD_KEY_PASSWORD`. When they're absent the release AAB/APK builds
**unsigned** (unchanged prior behaviour) — install/upload will fail until it's
signed. `versionCode` defaults to `1` locally; always drive it from CI so a
second Play upload doesn't reuse it.

> **M1-001 (pending):** Play now requires `targetSdk 35`, which needs Capacitor 7
> + AGP ≥ 8.6 + a Gradle 8.7+ wrapper + a regenerated `package-lock.json` and a
> device smoke on Android 15. Not done in this checkout — see `FIX_PLAN`.

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
- Push (M1-009): the web app registers for `@capacitor/push-notifications` on
  login (native shells only — `web/src/lib/native.ts::registerForPushNotifications`,
  wired in `AuthContext`) and PATCHes the resulting device token to
  `/auth/me/` `{ pushToken }`. No new notification product — just device-token
  capture. **This is dead on arrival until Firebase is provisioned**:
  1. Create a Firebase project, add an Android app with package name
     `in.bizboard.app` (matches `android/app/build.gradle`'s `applicationId`).
  2. Download `google-services.json` and place it at
     `android/app/google-services.json` (gitignored — never commit it).
     `build.gradle` only applies the `com.google.gms.google-services` plugin
     when that file exists; it's a silent no-op without it.
  3. `cap sync android`, rebuild. `PushNotifications.register()` will then
     actually reach FCM instead of failing silently.
  4. iOS needs the equivalent APNs/`GoogleService-Info.plist` setup — not
     done here.
- Deep links (M1-008): the custom scheme `in.bizboard.app://` is wired end to
  end — `AndroidManifest.xml`'s `VIEW`/`BROWSABLE` intent-filter,
  `MainActivity.onNewIntent`, and the web app's `@capacitor/app` listener
  (`native.ts::onDeepLink`, wired in `AuthContext`) route
  `in.bizboard.app://<path>` straight into the existing app shell's router.
  An `https://` **App Link** (so a real web URL also opens the app) is *not*
  done — that needs a production domain hosting `/.well-known/assetlinks.json`
  with `autoVerify="true"`, which this repo doesn't have configured.
- Outbox: IndexedDB wins when both IDB and Preferences have a copy. Web without Capacitor uses localStorage + IDB only.
