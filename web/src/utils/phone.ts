/**
 * Mobile numbers are stored as E.164 (`+<country code><number>`, e.g. +919876543210).
 * The form splits that into a country picker and the national digits; these
 * helpers convert between the two and say whether the number is complete.
 */

export type PhoneCountry = {
  /** ISO 3166-1 alpha-2. */
  iso: string;
  name: string;
  /** Calling code without the `+`. */
  dial: string;
  /** Allowed length of the national number (digits after the calling code). */
  min: number;
  max: number;
  /** Extra rule on the national number, when the country has a simple one. */
  pattern?: RegExp;
};

export const DEFAULT_PHONE_COUNTRY = 'IN';

// India first (most users), then the countries Indian traders deal with most.
export const PHONE_COUNTRIES: readonly PhoneCountry[] = [
  { iso: 'IN', name: 'India', dial: '91', min: 10, max: 10, pattern: /^[6-9]\d{9}$/ },
  { iso: 'AE', name: 'United Arab Emirates', dial: '971', min: 8, max: 9 },
  { iso: 'SA', name: 'Saudi Arabia', dial: '966', min: 9, max: 9 },
  { iso: 'QA', name: 'Qatar', dial: '974', min: 8, max: 8 },
  { iso: 'OM', name: 'Oman', dial: '968', min: 8, max: 8 },
  { iso: 'KW', name: 'Kuwait', dial: '965', min: 8, max: 8 },
  { iso: 'BH', name: 'Bahrain', dial: '973', min: 8, max: 8 },
  { iso: 'NP', name: 'Nepal', dial: '977', min: 8, max: 10 },
  { iso: 'BD', name: 'Bangladesh', dial: '880', min: 10, max: 10 },
  { iso: 'LK', name: 'Sri Lanka', dial: '94', min: 9, max: 9 },
  { iso: 'BT', name: 'Bhutan', dial: '975', min: 7, max: 8 },
  { iso: 'SG', name: 'Singapore', dial: '65', min: 8, max: 8 },
  { iso: 'MY', name: 'Malaysia', dial: '60', min: 9, max: 10 },
  { iso: 'US', name: 'United States / Canada', dial: '1', min: 10, max: 10 },
  { iso: 'GB', name: 'United Kingdom', dial: '44', min: 10, max: 10 },
  { iso: 'AU', name: 'Australia', dial: '61', min: 9, max: 9 },
  { iso: 'DE', name: 'Germany', dial: '49', min: 10, max: 11 },
];

export function findPhoneCountry(iso: string): PhoneCountry {
  return PHONE_COUNTRIES.find((c) => c.iso === iso) ?? PHONE_COUNTRIES[0];
}

/**
 * Clean what the user typed or pasted into national digits for `country`:
 * drops spaces/punctuation, a pasted `+<code>` / `<code>` prefix and a trunk `0`.
 */
export function cleanNationalNumber(input: string, country: PhoneCountry): string {
  let digits = input.replace(/\D/g, '');
  const pastedIntl = /^\s*(\+|00)/.test(input);
  if (pastedIntl) digits = digits.replace(/^00/, '');
  // Drop the calling code only when it is clearly there: an international paste,
  // or code + a whole number (919876543210). An 11th digit typed onto 9198765432
  // is not a calling code.
  const rest = digits.slice(country.dial.length).replace(/^0/, '');
  const codePlusNumber = digits.length > country.max && rest.length >= country.min && rest.length <= country.max;
  if (digits.startsWith(country.dial) && (pastedIntl || codePlusNumber)) {
    digits = digits.slice(country.dial.length);
  }
  // No national number in the list starts with 0 — a leading 0 is the trunk prefix (09876543210).
  digits = digits.replace(/^0+/, '');
  return digits.slice(0, country.max);
}

const BY_LONGEST_DIAL = [...PHONE_COUNTRIES].sort((a, b) => b.dial.length - a.dial.length);

/** The listed country whose calling code starts this international number, if any. */
export function countryForCallingCode(international: string): PhoneCountry | undefined {
  const digits = international.replace(/\D/g, '').replace(/^00/, '');
  // Longest calling code wins (+971 before +9…).
  return BY_LONGEST_DIAL.find((c) => digits.startsWith(c.dial));
}

/** Split a stored E.164 value into a country and its national digits. */
export function splitPhone(value: string | null | undefined): { iso: string; national: string } {
  const raw = (value ?? '').trim();
  if (!raw) return { iso: DEFAULT_PHONE_COUNTRY, national: '' };
  if (raw.startsWith('+')) {
    const match = countryForCallingCode(raw);
    if (match) return { iso: match.iso, national: raw.replace(/\D/g, '').slice(match.dial.length) };
  }
  const india = findPhoneCountry(DEFAULT_PHONE_COUNTRY);
  return { iso: india.iso, national: cleanNationalNumber(raw, india) };
}

/** Join a country and national digits into E.164; blank digits mean "no number". */
export function joinPhone(iso: string, national: string): string {
  const digits = national.replace(/\D/g, '');
  if (!digits) return '';
  return `+${findPhoneCountry(iso).dial}${digits}`;
}

/** True when the national number is complete and plausible for its country. */
export function isValidNationalNumber(country: PhoneCountry, national: string): boolean {
  if (!/^\d+$/.test(national)) return false;
  if (national.length < country.min || national.length > country.max) return false;
  return country.pattern ? country.pattern.test(national) : true;
}

/** True for a blank value or a complete E.164 number from the country list. */
export function isValidPhoneValue(value: string | null | undefined): boolean {
  const raw = (value ?? '').trim();
  if (!raw) return true;
  if (!raw.startsWith('+')) return false;
  const { iso, national } = splitPhone(raw);
  return isValidNationalNumber(findPhoneCountry(iso), national);
}
