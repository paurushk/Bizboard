import { isValidPincode } from '@/utils/gst';

/** India Post PIN. Blank is allowed; a non-blank value must pass isValidPincode. */
export function isValidIndianPincode(value: string): boolean {
  const text = value.trim();
  if (!text) return true;
  return isValidPincode(text);
}
