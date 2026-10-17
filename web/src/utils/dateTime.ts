/** A readable local date and time for list rows. Returns an empty string for a missing or invalid value. */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '';
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) return '';
  return at.toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' });
}
