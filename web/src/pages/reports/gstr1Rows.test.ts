import { describe, expect, it } from 'vitest';
import { documentIdsOf, gstr1RowPath, sectionRows } from '@/pages/reports/gstr1Rows';

describe('sectionRows', () => {
  it('reads a plain list', () => {
    expect(sectionRows([{ a: 1 }, { a: 2 }])).toHaveLength(2);
  });
  it('reads a list held under rows or docs', () => {
    expect(sectionRows({ rows: [{ a: 1 }] })).toHaveLength(1);
    expect(sectionRows({ docs: [{ a: 1 }, { a: 2 }] })).toHaveLength(2);
  });
  it('is empty for anything else', () => {
    expect(sectionRows(undefined)).toEqual([]);
    expect(sectionRows({ total: 3 })).toEqual([]);
    expect(sectionRows([1, 'x', null])).toEqual([]);
  });
});

describe('gstr1RowPath', () => {
  const ids = { sales_invoice: { 'INV-1': 7 }, sales_credit_note: { 'CN-1': 8 }, sales_debit_note: { 'DN-1': 9 } };
  it('opens an invoice, a credit note or a debit note', () => {
    expect(gstr1RowPath({ invoice_number: 'INV-1' }, ids)).toBe('/sales/history/7');
    expect(gstr1RowPath({ note_number: 'CN-1', note_kind: 'CREDIT' }, ids)).toBe('/sales/credit-notes/8');
    expect(gstr1RowPath({ note_number: 'DN-1', note_kind: 'DEBIT' }, ids)).toBe('/sales/debit-notes/9');
  });
  it('gives no link when the id is unknown', () => {
    expect(gstr1RowPath({ invoice_number: 'INV-X' }, ids)).toBeNull();
    expect(gstr1RowPath({ invoice_number: 'INV-1' }, undefined)).toBeNull();
    expect(gstr1RowPath({}, ids)).toBeNull();
  });
  it('reads the ids in either spelling', () => {
    expect(documentIdsOf({ documentIds: ids })).toBe(ids);
    expect(documentIdsOf({ document_ids: ids })).toBe(ids);
    expect(documentIdsOf({})).toBeUndefined();
  });
});
