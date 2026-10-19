/** Display helpers for the care, jobs and contracts screens. Pure functions, no React. */

/** A date-only value (YYYY-MM-DD) shown as the same calendar day in every time zone. */
export function formatDay(value: string | null | undefined): string {
  if (!value) return '';
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(value);
  if (!match) return '';
  const day = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
  if (Number.isNaN(day.getTime())) return '';
  return day.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
}

/** A date and time, in the viewer's zone. */
export function formatStamp(iso: string | null | undefined): string {
  if (!iso) return '';
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) return '';
  return at.toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' });
}

/** Whole days between now and a date-only value; negative once past. */
export function daysFromToday(value: string | null | undefined, now = new Date()): number | null {
  if (!value) return null;
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(value);
  if (!match) return null;
  const target = Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
  const today = Date.UTC(now.getFullYear(), now.getMonth(), now.getDate());
  return Math.round((target - today) / 86_400_000);
}

/** "3h 20m", "2d 4h", "45m". */
export function formatSpan(totalSeconds: number | null | undefined): string {
  if (totalSeconds == null || !Number.isFinite(totalSeconds)) return '';
  const minutes = Math.max(0, Math.round(Math.abs(totalSeconds) / 60));
  const days = Math.floor(minutes / 1440);
  const hours = Math.floor((minutes % 1440) / 60);
  const rest = minutes % 60;
  if (days > 0) return hours ? `${days}d ${hours}h` : `${days}d`;
  if (hours > 0) return rest ? `${hours}h ${rest}m` : `${hours}h`;
  return `${rest}m`;
}

/** Age of a record from its created stamp: "5d", "3h", "just now" style handled by the caller. */
export function ageSeconds(iso: string | null | undefined, now = Date.now()): number | null {
  if (!iso) return null;
  const at = Date.parse(iso);
  return Number.isFinite(at) ? Math.max(0, Math.round((now - at) / 1000)) : null;
}

/** Local-date input value for today plus an offset in days. */
export function dayInput(offsetDays = 0, now = new Date()): string {
  const day = new Date(now.getFullYear(), now.getMonth(), now.getDate() + offsetDays);
  const month = String(day.getMonth() + 1).padStart(2, '0');
  const date = String(day.getDate()).padStart(2, '0');
  return `${day.getFullYear()}-${month}-${date}`;
}

/** Value for <input type="datetime-local"> from an ISO stamp, in local time. */
export function toLocalInput(iso: string | null | undefined): string {
  if (!iso) return '';
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) return '';
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${at.getFullYear()}-${pad(at.getMonth() + 1)}-${pad(at.getDate())}T${pad(at.getHours())}:${pad(at.getMinutes())}`;
}

/** ISO stamp from a datetime-local value (local time), or undefined when blank. */
export function fromLocalInput(value: string): string | undefined {
  if (!value) return undefined;
  const at = new Date(value);
  return Number.isNaN(at.getTime()) ? undefined : at.toISOString();
}

/** A number as a trimmed decimal: "5.000" -> "5". */
export function plainNumber(value: string | number | null | undefined): string {
  if (value == null || value === '') return '';
  const n = Number(value);
  if (!Number.isFinite(n)) return String(value);
  return String(Number(n.toFixed(3)));
}
