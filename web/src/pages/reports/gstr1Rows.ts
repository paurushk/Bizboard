export type Row = Record<string, unknown>;

/** A section can arrive as a list, or as an object that holds its list under rows or docs. */
export function sectionRows(value: unknown): Row[] {
  if (Array.isArray(value)) return value.filter((r): r is Row => !!r && typeof r === 'object');
  if (value && typeof value === 'object') {
    const obj = value as Row;
    for (const k of ['rows', 'docs', 'items']) {
      if (Array.isArray(obj[k])) return sectionRows(obj[k]);
    }
  }
  return [];
}

type IdMap = Record<string, Record<string, number>>;

/** Where the document behind a GSTR-1 row lives, from the ids the server sends beside the tables. */
export function gstr1RowPath(row: Row, ids: IdMap | undefined): string | null {
  if (!ids) return null;
  const invoice = typeof row.invoice_number === 'string' ? row.invoice_number : null;
  if (invoice) {
    const id = ids.sales_invoice?.[invoice];
    return id == null ? null : `/sales/history/${id}`;
  }
  const note = typeof row.note_number === 'string' ? row.note_number : null;
  if (note) {
    const debit = row.note_kind === 'DEBIT';
    const id = ids[debit ? 'sales_debit_note' : 'sales_credit_note']?.[note];
    return id == null ? null : `/sales/${debit ? 'debit-notes' : 'credit-notes'}/${id}`;
  }
  return null;
}

export function documentIdsOf(data: Row): IdMap | undefined {
  const raw = data.document_ids ?? data.documentIds;
  return raw && typeof raw === 'object' ? (raw as IdMap) : undefined;
}
