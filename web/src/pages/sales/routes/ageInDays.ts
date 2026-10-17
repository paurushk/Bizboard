const DAY_MS = 24 * 60 * 60 * 1000;

/** Whole days since an ISO timestamp (0 when it is today or unreadable). */
export function ageInDays(createdAt: string | undefined, now: number = Date.now()): number {
  if (!createdAt) return 0;
  const then = Date.parse(createdAt);
  if (!Number.isFinite(then)) return 0;
  return Math.max(0, Math.floor((now - then) / DAY_MS));
}
