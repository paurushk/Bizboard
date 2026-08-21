// BB-000580: installable app-shell PWA.
// Honesty: Background Sync / periodic sync is not guaranteed on iOS (Safari or
// home-screen PWAs). Invoice drafts still use the IndexedDB outbox in
// invoiceDraftCache.ts — users must reopen the app online to flush.

export function registerPwa() {
  if (!import.meta.env.PROD) return;
  void import('virtual:pwa-register')
    .then(({ registerSW }) => {
      registerSW({ immediate: true });
    })
    .catch(() => {
      // Plugin unavailable in unit tests or misconfigured builds.
    });
}
