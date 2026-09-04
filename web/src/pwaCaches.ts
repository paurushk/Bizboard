/** BB-000738: purge Workbox caches that may hold tenant JSON or shell pages. */

export async function clearBizboardPwaCaches(): Promise<void> {
  if (typeof caches === 'undefined') return;
  try {
    // F1-019: enumerate every `bizboard-*` cache rather than a hard-coded list
    // (which named `bizboard-api`, a cache the current Workbox config never
    // creates) — covers any future runtime-cache name automatically.
    const keys = await caches.keys();
    await Promise.all(
      keys.filter((name) => /^bizboard-/.test(name)).map((name) => caches.delete(name)),
    );
  } catch {
    // best-effort — Cache Storage may be unavailable in private mode / tests
  }
}
