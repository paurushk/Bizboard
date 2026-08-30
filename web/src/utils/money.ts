import { getLocale } from '@/i18n';

function numberLocale(): string {
  return getLocale() === 'hi' ? 'hi-IN' : 'en-IN';
}

/** Round to 2 decimal places using ROUND_HALF_UP (matches Python Decimal q2).
 *
 * R5-005: this operates on a binary float via toFixed(10); the backend uses
 * exact Decimal. On adversarial inputs the FE preview total can differ from the
 * posted document by ~1 paise. The UI must always treat the server totals as
 * authoritative once a document is saved. */
export function roundMoney(value: number): number {
  if (!Number.isFinite(value)) return 0;
  if (Math.abs(value) >= 1e21) return value;
  const sign = value < 0 ? -1 : 1;
  const abs = Math.abs(value);
  // Read the true decimal expansion (10dp) instead of scaling the binary
  // float and adding an epsilon fudge factor.
  const fixed = abs.toFixed(10);
  const dot = fixed.indexOf('.');
  if (dot === -1) return value;
  const intDigits = fixed.slice(0, dot);
  const fracDigits = fixed.slice(dot + 1).padEnd(10, '0');
  let cents = BigInt(intDigits + fracDigits.slice(0, 2));
  const thirdDigit = fracDigits.charCodeAt(2) - 48;
  if (thirdDigit >= 5) cents += 1n;
  if (cents === 0n) return 0;
  return (sign * Number(cents)) / 100;
}

export function toNumber(value: string | number | null | undefined): number {
  if (value == null || value === '') return 0;
  const n = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(n) ? n : 0;
}

export function formatMoney(value: string | number | null | undefined, currency = 'INR'): string {
  return new Intl.NumberFormat(numberLocale(), {
    style: 'currency',
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(toNumber(value));
}

export function formatNumber(value: string | number | null | undefined, digits = 2): string {
  return new Intl.NumberFormat(numberLocale(), {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(toNumber(value));
}
