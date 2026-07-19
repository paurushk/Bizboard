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

export function normalizeGstRate(rate: number): number {
  const allowed = [0, 5, 12, 18, 28];
  if (allowed.includes(rate)) return rate;
  return Math.max(0, Math.min(28, rate));
}
