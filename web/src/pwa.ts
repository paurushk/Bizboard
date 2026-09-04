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
        // F1-003: vite.config.ts uses registerType: 'prompt' so this handler
        // fires when a new worker is waiting. Confirm before reloading so an
        // in-progress invoice / POS entry isn't wiped by a deploy.
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
