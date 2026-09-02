// BB-000580: installable app-shell PWA.
// Honesty: Background Sync / periodic sync is not guaranteed on iOS (Safari or
// home-screen PWAs). Invoice drafts still use the IndexedDB outbox in
// invoiceDraftCache.ts — users must reopen the app online to flush.

export function registerPwa() {
  if (!import.meta.env.PROD) return;
  void import('virtual:pwa-register')
    .then(({ registerSW }) => {
      const updateSW = registerSW({
        immediate: true,
        // After a Docker/web rebuild the old SW kept serving yesterday's JS,
        // so Upload/extract fixes looked "not deployed". Apply the new worker
        // and reload once so every later deploy takes effect without Ctrl+F5.
        onNeedRefresh() {
          if (window.confirm('A new version is available. Reload now?')) {
            void updateSW(true);
          }
        },
      });
    })
    .catch(() => {
      // Plugin unavailable in unit tests or misconfigured builds.
    });
}
