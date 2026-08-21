/** BB-000738: purge Workbox caches that may hold tenant JSON or shell pages. */

const PWA_CACHE_NAMES = ['bizboard-api', 'bizboard-pages'] as const;

export async function clearBizboardPwaCaches(): Promise<void> {
  if (typeof caches === 'undefined') return;
  try {
    await Promise.all(PWA_CACHE_NAMES.map((name) => caches.delete(name)));
  } catch {
    // best-effort — Cache Storage may be unavailable in private mode / tests
  }
}
