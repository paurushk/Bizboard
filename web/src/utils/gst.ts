/** Validate Indian GSTIN format (15 chars). Live GSTN check is Phase 2. */
export function isValidGstin(gstin: string): boolean {
  if (!gstin) return false;
  const normalized = gstin.trim().toUpperCase();
  const pattern =
    /^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$/;
  return pattern.test(normalized);
}

/** HSN/SAC: 4, 6, or 8 digits for MVP format check. */
export function isValidHsnSac(code: string): boolean {
  if (!code) return false;
  return /^[0-9]{4}([0-9]{2})?([0-9]{2})?$/.test(code.trim());
}

const ALLOWED_GST_RATES = [0, 0.25, 3, 5, 12, 18, 28];

/** Snap an arbitrary rate to the nearest official GST slab (BUG-416) —
 * previously this only clamped to [0, 28], so an in-range-but-invalid rate
 * like 15 or 22 passed through unchanged despite the function's name
 * implying real-slab normalization. */
export function normalizeGstRate(rate: number): number {
  if (!Number.isFinite(rate)) return 0;
  return ALLOWED_GST_RATES.reduce((closest, candidate) =>
    Math.abs(candidate - rate) < Math.abs(closest - rate) ? candidate : closest,
  );
}
