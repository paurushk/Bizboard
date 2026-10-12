/** GSTN unit quantity codes that are sold by measure, so a fractional quantity is valid. */
const DECIMAL_UQC = new Set([
  'KGS', 'GMS', 'QTL', 'TON', 'MTS', 'LTR', 'MLT', 'MTR', 'CMS', 'SQM', 'SQF', 'SQY', 'CBM', 'KLR', 'KME',
]);

export type QuantityPolicy = { decimals: boolean; min: number; step: number };

/** Whole-unit goods (pcs, box…) stay integer; measured goods may carry up to three decimals. */
export function quantityPolicy(uqc?: string | null): QuantityPolicy {
  const decimals = DECIMAL_UQC.has((uqc ?? '').trim().toUpperCase());
  return decimals ? { decimals: true, min: 0.001, step: 0.5 } : { decimals: false, min: 1, step: 1 };
}

/** Parse what the rep typed. Returns null when it is not a valid quantity for the policy. */
export function parseQuantity(raw: string, policy: QuantityPolicy): number | null {
  const text = raw.trim();
  // Plain decimal digits only: Number() would also accept "0x10", "1e2" or "Infinity".
  if (!/^\d+(\.\d+)?$/.test(text)) return null;
  const n = Number(text);
  if (!Number.isFinite(n)) return null;
  if (!policy.decimals && !Number.isInteger(n)) return null;
  if (n < policy.min) return null;
  return policy.decimals ? Math.round(n * 1000) / 1000 : n;
}

export function formatQuantity(n: number): string {
  return String(Math.round(n * 1000) / 1000);
}
