/** List label: trailing sequence plus financial year. The stored number stays the title and the search key. */

export function financialYearLabel(iso?: string | null): string {
  if (!iso) return '';
  const date = new Date(`${iso.slice(0, 10)}T00:00:00`);
  if (Number.isNaN(date.getTime())) return '';
  const year = date.getFullYear();
  const start = date.getMonth() + 1 >= 4 ? year : year - 1;
  const end = String((start + 1) % 100).padStart(2, '0');
  return `${start}-${end}`;
}

export function shortDocumentNumber(number: string, isoDate?: string | null): string {
  const full = number.trim();
  const fy = financialYearLabel(isoDate);
  const match = full.match(/^([A-Za-z]+)-0*(\d+)$/);
  const core = match ? `${match[1]}-${Number(match[2])}` : full;
  return fy ? `${core} · ${fy}` : core;
}

/** Send the stored form so "INV-13" finds "INV-00013". */
export function documentSearchQuery(query: string): string {
  const core = query.split('·')[0]?.trim() ?? query.trim();
  const match = core.match(/^([A-Za-z]+)-(\d+)$/);
  if (!match) return query.trim();
  if (match[2].length >= 5) return core;
  return `${match[1]}-${match[2].padStart(5, '0')}`;
}
