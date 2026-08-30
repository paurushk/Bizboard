/** Validate Indian GSTIN format (15 chars) + mod-36 checksum. */
export function isValidGstin(gstin: string): boolean {
  if (!gstin) return false;
  const normalized = gstin.trim().toUpperCase();
  const pattern =
    /^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$/;
  if (!pattern.test(normalized)) return false;
  const chars = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ';
  let total = 0;
  for (let i = 0; i < 14; i += 1) {
    const code = chars.indexOf(normalized[i]);
    if (code < 0) return false;
    const factor = 1 + (i % 2);
    const product = code * factor;
    total += Math.floor(product / 36) + (product % 36);
  }
  const check = (36 - (total % 36)) % 36;
  return chars[check] === normalized[14];
}

/** Indian PAN: 5 letters + 4 digits + 1 letter (AAAAA9999A). */
export function isValidPan(pan: string): boolean {
  if (!pan) return false;
  return /^[A-Z]{5}[0-9]{4}[A-Z]$/.test(pan.trim().toUpperCase());
}

/** Indian IFSC: 4 letters + 0 + 6 alphanumeric. */
export function isValidIfsc(ifsc: string): boolean {
  if (!ifsc) return false;
  return /^[A-Z]{4}0[A-Z0-9]{6}$/.test(ifsc.trim().toUpperCase());
}

/** Indian mobile number: 10 digits, first digit 6-9. Ignores spaces/hyphens and an optional +91/0 prefix. */
export function isValidIndianPhone(phone: string): boolean {
  if (!phone) return false;
  const digits = phone.trim().replace(/[\s-]/g, '').replace(/^(\+?91|0)/, '');
  return /^[6-9][0-9]{9}$/.test(digits);
}

/** Indian PIN code: exactly 6 digits. */
export function isValidPincode(pin: string): boolean {
  if (!pin) return false;
  return /^\d{6}$/.test(pin.trim());
}

/** HSN/SAC: 4, 6, or 8 digits for MVP format check. */
export function isValidHsnSac(code: string): boolean {
  if (!code) return false;
  return /^[0-9]{4}([0-9]{2})?([0-9]{2})?$/.test(code.trim());
}

/** UPI VPA: local-part @ PSP handle (PAY-13). */
export function isValidUpiVpa(vpa: string): boolean {
  if (!vpa) return false;
  return /^[a-zA-Z0-9.\-_]{2,256}@[a-zA-Z]{2,64}$/.test(vpa.trim());
}

export const ALLOWED_GST_RATES = [0, 0.25, 3, 5, 12, 18, 28, 40];

const GST_RATE_LABELS: Record<number, string> = {
  0: '0% (Exempt / Nil)',
  0.25: '0.25% (Precious Stones)',
  3: '3% (Gold / Silver)',
  5: '5%',
  12: '12%',
  18: '18% (Standard Goods & Services)',
  28: '28% (Luxury & Demerit)',
  40: '40%',
};

export const GST_RATE_OPTIONS = ALLOWED_GST_RATES.map((value) => ({
  value: String(value),
  label: GST_RATE_LABELS[value] ?? `${value}%`,
}));

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
