/**
 * CSV export helpers for client-built exports.
 *
 * Mirrors the backend `core.csv_utils.csv_safe`: a value whose first (non-space)
 * character is `= + - @` or a tab/CR/LF is a spreadsheet formula-injection
 * vector, so it is prefixed with a single quote before quoting. Numeric-looking
 * negatives (e.g. `-42.5`) are left alone so Excel still parses them as numbers.
 */

const FORMULA_LEAD = /^[=+@\t\r\n]/;
const NEGATIVE_NUMBER = /^-\d[\d,]*(\.\d+)?$/;

/** Neutralise formula injection, returning the raw (still-unquoted) text. */
export function csvSafe(value: unknown): string {
  if (value === null || value === undefined) return '';
  const text = String(value);
  if (!text) return text;
  const stripped = text.replace(/^\s+/, '');
  if (stripped.startsWith('-')) {
    return NEGATIVE_NUMBER.test(stripped) ? text : `'${text}`;
  }
  if (FORMULA_LEAD.test(stripped) || FORMULA_LEAD.test(text)) return `'${text}`;
  return text;
}

/** Formula-safe + RFC-4180 quoted CSV cell. */
export function csvCell(value: unknown): string {
  return `"${csvSafe(value).replace(/"/g, '""')}"`;
}

/** Join rows (arrays of cell values) into a CSV string with CRLF line endings. */
export function toCsv(rows: unknown[][]): string {
  return rows.map((row) => row.map(csvCell).join(',')).join('\r\n');
}
