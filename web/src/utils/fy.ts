/** Indian financial-year helpers (FY runs 1 Apr – 31 Mar). */

/**
 * F3-062: the next 31 March on or after `from` (default today), as an ISO date.
 * Used to default "FY end" pickers so they never go stale after a year rolls.
 */
export function nextIndianFyEnd(from: Date = new Date()): string {
  const year = from.getMonth() >= 3 ? from.getFullYear() + 1 : from.getFullYear();
  return `${year}-03-31`;
}
