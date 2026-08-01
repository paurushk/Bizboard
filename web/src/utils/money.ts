/** Round to 2 decimal places using ROUND_HALF_UP (matches Python Decimal q2). */
export function roundMoney(value: number): number {
  if (!Number.isFinite(value)) return 0;
  const sign = value < 0 ? -1 : 1;
  const abs = Math.abs(value);
  // Read the true decimal expansion (10dp) instead of scaling the binary
  // float and adding an epsilon fudge factor. The old scale-by-100-plus-epsilon
  // approach let float representation error flip the rounding direction on a
  // measurable fraction of real qty/price/rate combinations (BUG-201/400) —
  // `toFixed` reports the float's faithful decimal value, so reading 10
  // fractional digits (vs. the 2 we actually need) leaves enough margin for
  // any realistic invoice-arithmetic float error to resolve to the correct
  // side of the rounding boundary.
  const fixed = abs.toFixed(10);
  const dot = fixed.indexOf('.');
  const intDigits = fixed.slice(0, dot);
  const fracDigits = fixed.slice(dot + 1).padEnd(10, '0');
  let cents = BigInt(intDigits + fracDigits.slice(0, 2));
  const thirdDigit = fracDigits.charCodeAt(2) - 48;
  if (thirdDigit >= 5) cents += 1n;
  return (sign * Number(cents)) / 100;
}

export function toNumber(value: string | number | null | undefined): number {
  if (value == null || value === '') return 0;
  const n = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(n) ? n : 0;
}

export function formatMoney(value: string | number | null | undefined, currency = 'INR'): string {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(toNumber(value));
}

export function formatNumber(value: string | number | null | undefined, digits = 2): string {
  return new Intl.NumberFormat('en-IN', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(toNumber(value));
}
