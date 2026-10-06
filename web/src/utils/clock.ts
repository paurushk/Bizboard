/** Display-only time checks (overdue chips, stale reviews). Components call these instead of reading the clock in render. */

export function isPastIso(iso: string | null | undefined): boolean {
  if (!iso) return false;
  const at = new Date(iso).getTime();
  return Number.isFinite(at) && at < Date.now();
}

export function isOlderThanMs(iso: string | null | undefined, ms: number): boolean {
  if (!iso) return false;
  const at = Date.parse(iso);
  return Number.isFinite(at) && Date.now() - at > ms;
}
