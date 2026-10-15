/**
 * How long bill extraction has taken for this browser's recent uploads, so the wait can be described
 * from what actually happened here instead of a guess. Kept in localStorage only.
 */
const KEY = 'bizboard:billUpload:extractionSeconds';
const KEEP = 10;
const MIN_SAMPLES = 2;

function read(): number[] {
  try {
    const parsed = JSON.parse(localStorage.getItem(KEY) ?? '[]') as unknown;
    return Array.isArray(parsed) ? parsed.filter((n): n is number => typeof n === 'number' && n > 0) : [];
  } catch {
    return [];
  }
}

export function recordExtractionSeconds(seconds: number): void {
  if (!Number.isFinite(seconds) || seconds <= 0) return;
  try {
    localStorage.setItem(KEY, JSON.stringify([...read(), Math.round(seconds)].slice(-KEEP)));
  } catch {
    // Private mode: the page simply keeps the generic wording.
  }
}

/** Median of the recent durations in whole minutes (at least 1), or null with too little history. */
export function typicalExtractionMinutes(): { minutes: number; samples: number } | null {
  const values = read();
  if (values.length < MIN_SAMPLES) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  const median = sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
  return { minutes: Math.max(1, Math.round(median / 60)), samples: sorted.length };
}
