export type BooksBannerState = 'unknown' | 'off' | 'no-chart' | 'backfill' | 'ties';

/** Which books message a report may show. Copy only: no chart is created from the screen. */
export function booksBannerState(input: {
  loaded: boolean;
  accountingEnabled: boolean;
  backfillNeeded: boolean;
  accountCount: number | null;
}): BooksBannerState {
  if (!input.loaded) return 'unknown';
  if (!input.accountingEnabled) return 'off';
  if (input.accountCount === 0) return 'no-chart';
  if (input.backfillNeeded) return 'backfill';
  return 'ties';
}

/** Totals are a dash while the chart is missing or older documents are not posted. */
export function booksTotalsTrusted(state: BooksBannerState): boolean {
  return state === 'ties' || state === 'off' || state === 'unknown';
}
