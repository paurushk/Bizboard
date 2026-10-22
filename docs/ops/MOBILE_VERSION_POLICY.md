# Mobile app version policy (WP-L1)

The Android app is a Capacitor shell. Its WebView loads the live web app from the server
(`CAPACITOR_SERVER_URL`), so screens and API calls are always current. What can go stale is the
**shell**: native plugins (push, network status, deep links, scanner bridges) and the WebView
settings in `mobile/capacitor.config.ts`.

## How the API knows the build

- The shell appends `BizBoardApp/<version>` to its user agent (`BIZBOARD_APP_VERSION`, set at build
  time and kept equal to the Gradle `versionName`).
- The web app reads it (`nativeAppVersion()` in `web/src/api/client.ts`) and sends
  `X-App-Version` on every API call. Browsers send nothing.
- `MIN_SUPPORTED_APP_VERSION` on the server (empty = no floor). A call from an older build gets
  **HTTP 426** with code `APP_UPDATE_REQUIRED` and the message "This version of the BizBoard app is
  no longer supported. Update it from the Play Store to continue." Health and the CSRF cookie stay
  reachable (`core.middleware.AppVersionMiddleware`).

## Policy

1. Support the **last two released shell versions, or 90 days**, whichever is longer.
2. Raise `MIN_SUPPORTED_APP_VERSION` only when a server or web change needs a newer shell
   (a new native plugin, a changed deep-link scheme). Announce it in the app a week before.
3. Before raising it, check how many active devices are below the new floor (Play Console →
   Android vitals → versions). If more than 10% are, wait.
4. Every release: bump `bizboardVersionName` / `bizboardVersionCode` (Gradle) and
   `BIZBOARD_APP_VERSION` (CI variable) together.

## Release process (Play Store) [Human]

1. Tag the release; CI `mobile-apk` builds the APK/AAB with the version above.
2. Upload to the Play Console internal track; install on two real devices; run the smoke in
   `mobile/e2e`.
3. Promote to production with staged rollout (10% → 50% → 100% over a week).
4. Record the version, date and floor change here.

| Date | Shell version | Floor (`MIN_SUPPORTED_APP_VERSION`) | Notes |
|---|---|---|---|
| | | | |
