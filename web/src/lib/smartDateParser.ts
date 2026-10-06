/**
 * Smart date parser for high-velocity keyboard entry of batch expiry and manufacturing dates.
 * Enforces unambiguous grammar and prevents past expiry dates.
 */

export interface SmartDateResult {
  ok: true;
  dateIso: string; // YYYY-MM-DD
  formatted: string; // DD/MM/YYYY
  preview: string; // Human-readable e.g. "Aug 31, 2028"
}

export type SmartDateErrorCode = 'required' | 'chars' | 'format' | 'year' | 'month' | 'day' | 'past';

export interface SmartDateError {
  ok: false;
  error: string;
  code: SmartDateErrorCode;
  maxDays?: number;
}

export type SmartDateParse = SmartDateResult | SmartDateError;

function pad(n: number): string {
  return n < 10 ? `0${n}` : `${n}`;
}

/** Calendar date in the runtime timezone. UTC ISO shifts the day for India before 05:30. */
function localIsoDate(d: Date): string {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** ISO date when the shorthand is valid; otherwise the trimmed raw text. */
export function toIsoDateOrRaw(value: string, allowPast = false): string | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const parsed = parseSmartExpiryDate(trimmed, { allowPast });
  return parsed.ok ? parsed.dateIso : trimmed;
}

function monthName(monthIndex: number): string {
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  return months[monthIndex] ?? '';
}

function getLastDayOfMonth(year: number, month1Based: number): number {
  return new Date(Date.UTC(year, month1Based, 0)).getUTCDate();
}

/**
 * Parses keyboard shorthand for batch expiry.
 * Supported grammars:
 * - MMYY (4 digits, e.g. "0828" -> 2028-08-31)
 * - MMYYYY (6 digits, e.g. "082028" -> 2028-08-31)
 * - DDMMYYYY (8 digits, e.g. "15082028" -> 2028-08-15)
 * - Standard formats with delimiters: "MM/YY", "MM/YYYY", "DD/MM/YYYY", "YYYY-MM-DD"
 */
export function parseSmartExpiryDate(input: string, options?: { allowPast?: boolean; now?: Date }): SmartDateParse {
  const raw = (input ?? '').trim();
  if (!raw) {
    return { ok: false, error: 'Date is required', code: 'required' };
  }

  // If already standard ISO YYYY-MM-DD
  if (/^\d{4}-\d{2}-\d{2}$/.test(raw)) {
    const [yStr, mStr, dStr] = raw.split('-');
    const year = Number(yStr);
    const month = Number(mStr);
    const day = Number(dStr);
    return validateAndBuildResult(year, month, day, options);
  }

  // Strip common separators (slashes, hyphens, dots, spaces)
  const digits = raw.replace(/[-/.\s]/g, '');
  if (!/^\d+$/.test(digits)) {
    return { ok: false, error: 'Only numbers and date separators are allowed', code: 'chars' };
  }

  let year: number;
  let month: number;
  let day: number;

  if (digits.length === 4) {
    // MMYY -> Expiry defaults to end of that month
    month = Number(digits.slice(0, 2));
    const shortYear = Number(digits.slice(2, 4));
    year = 2000 + shortYear;
    day = getLastDayOfMonth(year, month);
  } else if (digits.length === 6) {
    // MMYYYY
    month = Number(digits.slice(0, 2));
    year = Number(digits.slice(2, 6));
    day = getLastDayOfMonth(year, month);
  } else if (digits.length === 8) {
    // DDMMYYYY
    day = Number(digits.slice(0, 2));
    month = Number(digits.slice(2, 4));
    year = Number(digits.slice(4, 8));
  } else {
    return { ok: false, error: 'Enter date as MMYY (e.g. 0828) or DDMMYYYY', code: 'format' };
  }

  return validateAndBuildResult(year, month, day, options);
}

function validateAndBuildResult(
  year: number,
  month: number,
  day: number,
  options?: { allowPast?: boolean; now?: Date },
): SmartDateParse {
  if (year < 2000 || year > 2099) {
    return { ok: false, error: 'Year must be between 2000 and 2099', code: 'year' };
  }
  if (month < 1 || month > 12) {
    return { ok: false, error: 'Month must be between 01 and 12', code: 'month' };
  }

  const maxDays = getLastDayOfMonth(year, month);
  if (day < 1 || day > maxDays) {
    return { ok: false, error: `Day must be between 01 and ${maxDays}`, code: 'day', maxDays };
  }

  const dateIso = `${year}-${pad(month)}-${pad(day)}`;
  const formatted = `${pad(day)}/${pad(month)}/${year}`;
  const preview = `${monthName(month - 1)} ${day}, ${year}`;

  const now = options?.now ?? new Date();
  const todayIso = localIsoDate(now);

  if (!options?.allowPast && dateIso < todayIso) {
    return { ok: false, error: 'Expiry date cannot be in the past', code: 'past' };
  }

  return {
    ok: true,
    dateIso,
    formatted,
    preview,
  };
}
