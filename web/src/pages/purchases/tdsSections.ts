/** Statutory TDS sections for purchase bills (BUG-UI-014). */

export const TDS_SECTION_OPTIONS = [
  { code: '194C', labelKey: 'billing.tds194C' },
  { code: '194J', labelKey: 'billing.tds194J' },
  { code: '194I', labelKey: 'billing.tds194I' },
  { code: '194Q', labelKey: 'billing.tds194Q' },
] as const;

export type TdsSectionCode = (typeof TDS_SECTION_OPTIONS)[number]['code'];

/** 4th character of the PAN embedded in a GSTIN (index 5). P/H = individual or HUF. */
export function panFourthFromGstin(gstin?: string): string {
  const value = (gstin || '').trim().toUpperCase();
  return value.length >= 6 ? value[5] : '';
}

/**
 * Default withholding rate for a statutory section.
 * Company constitution is PAN 4th character C (GSTIN index 5); everyone else
 * uses the individual/HUF rate. 194C is 1% / 2%, 194J and 194I are 10% / 2%,
 * 194Q is 0.1%.
 */
export function statutoryTdsRate(section: string, gstin?: string): number | null {
  const company = panFourthFromGstin(gstin) === 'C';
  switch (section) {
    case '194C':
      return company ? 2 : 1;
    case '194J':
      return company ? 2 : 10;
    case '194I':
      return company ? 2 : 10;
    case '194Q':
      return 0.1;
    default:
      return null;
  }
}
