/** Round to 2 decimal places using ROUND_HALF_UP (matches Python Decimal q2). */
export function roundMoney(value: number): number {
  if (!Number.isFinite(value)) return 0;
  const sign = value < 0 ? -1 : 1;
  const abs = Math.abs(value);
  // Avoid binary float artifacts: scale via fixed string then half-up on the 3rd dp.
  const scaled = abs * 100;
  const floored = Math.floor(scaled + 1e-9);
  const frac = scaled - floored;
  const rounded = frac >= 0.5 - 1e-12 ? floored + 1 : floored;
  return (sign * rounded) / 100;
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
