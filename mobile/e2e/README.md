# Mobile e2e (SR-35)

`smoke.yaml` is a [Maestro](https://maestro.mobile.dev) flow run against the
pilot APK on a headless emulator in CI (`mobile-emulator-smoke` job, advisory /
`continue-on-error` until stable).

It covers, end to end:
- login on the packaged WebView shell
- **SR-32** session survives a cold `stopApp` / `launchApp`
- a counter sale completes (H-02 path)
- **SR-34** an offline draft is queued in airplane mode and flushes on reconnect

Deep-link routing (**SR-33**) is unit-tested in `web/src/lib/native.test.ts`
(`deepLinkToPath`); an emulator `adb shell am start -d in.bizboard.app://...`
step can be added here once the smoke is green.

Run locally:  `maestro test mobile/e2e/smoke.yaml`  (needs a running emulator +
the pilot APK installed and a reachable pilot backend).
