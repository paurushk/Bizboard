/**
 * F3-074: derive a short code from a free-text name for "code optional" forms
 * (cost centers, warehouses, …). Strips whitespace/punctuation first so the
 * generated code never contains spaces or symbols.
 */
export function codeFromName(name: string, maxLen = 8): string {
  const cleaned = name.replace(/[^a-zA-Z0-9]/g, '');
  return (cleaned || name.trim()).slice(0, maxLen).toUpperCase();
}
