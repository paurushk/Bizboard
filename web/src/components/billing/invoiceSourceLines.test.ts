import { describe, expect, it } from 'vitest';
import type { LineItem } from '@/types/domain';
import {
  hasSerialPickList,
  invoiceItemsToSourceLines,
  pickedSerials,
  sourceLineReturnPayload,
  toggleSerialPick,
  trimSerialsToQty,
} from './invoiceSourceLines';

function item(partial: Partial<LineItem> & Pick<LineItem, 'product'>): LineItem {
  return {
    product: partial.product,
    quantity: partial.quantity ?? 2,
    unitPrice: partial.unitPrice ?? 10,
    gstRate: partial.gstRate ?? 18,
    productName: partial.productName ?? 'Widget',
    serialNumbers: partial.serialNumbers,
    batch: partial.batch,
    batchNo: partial.batchNo,
    id: partial.id ?? 1,
  };
}

describe('invoiceItemsToSourceLines (R-007 / R-008)', () => {
  it('copies serials, trackSerial, and batch from the invoice line', () => {
    const lines = invoiceItemsToSourceLines(
      [item({ product: 9, id: 3, serialNumbers: ['SN-1', 'SN-2'], batch: 44, batchNo: 'LOT-A' })],
      undefined,
      new Map([[9, { trackSerial: true, trackBatch: true }]]),
    );
    expect(lines).toHaveLength(1);
    expect(lines[0].trackSerial).toBe(true);
    expect(lines[0].trackBatch).toBe(true);
    // Nothing is pre-picked; the sold serials are offered as a pick list.
    expect(lines[0].serialNumbersText).toBe('');
    expect(lines[0].soldSerialNumbers).toEqual(['SN-1', 'SN-2']);
    expect(lines[0].batchNo).toBe('LOT-A');
    expect(lines[0].batch).toBe(44);
  });
});

describe('sourceLineReturnPayload (R-007 / R-008)', () => {
  it('includes parsed serials and batch when present', () => {
    const [line] = invoiceItemsToSourceLines(
      [item({ product: 9, serialNumbers: ['A', 'B'], batch: 7, batchNo: 'L1' })],
      undefined,
      new Map([[9, { trackSerial: true, trackBatch: true }]]),
    );
    line.included = true;
    line.quantity = 2;
    line.serialNumbersText = 'A, B';
    expect(sourceLineReturnPayload(line, { includeBatch: true })).toEqual(
      expect.objectContaining({
        product: 9,
        quantity: 2,
        serialNumbers: ['A', 'B'],
        batch: 7,
      }),
    );
  });
});

describe('server headroom and serial picks (SRF-02 / SRF-06)', () => {
  const meta = new Map([[9, { trackSerial: true }]]);
  const sold = item({ product: 9, id: 5, quantity: 3, serialNumbers: ['S1', 'S2', 'S3'] });
  const row = (over: Partial<{ returnable: number; returnedSerials: string[] }> = {}) => ({
    sourceItem: 5,
    product: 9,
    productName: 'Widget',
    sold: 3,
    returned: 1,
    creditedStandalone: 0,
    returnable: 2,
    returnedSerials: ['S2'],
    ...over,
  });

  it('uses the server returnable quantity instead of client arithmetic', () => {
    const [line] = invoiceItemsToSourceLines([sold], new Map([[9, 99]]), meta, undefined, [row()]);
    expect(line.maxQty).toBe(2);
  });

  it('drops serials that already came back from the pick list', () => {
    const [line] = invoiceItemsToSourceLines([sold], undefined, meta, undefined, [row()]);
    expect(line.soldSerialNumbers).toEqual(['S1', 'S3']);
    expect(hasSerialPickList(line)).toBe(true);
  });

  it('falls back to client arithmetic for lines the server did not describe', () => {
    const [line] = invoiceItemsToSourceLines([sold], undefined, meta, new Map([[5, 1]]), []);
    expect(line.maxQty).toBe(2);
  });

  it('splits legacy unlinked product returns across lines in order', () => {
    const a = item({ product: 1, id: 1, quantity: 2 });
    const b = item({ product: 1, id: 2, quantity: 2 });
    const lines = invoiceItemsToSourceLines([a, b], new Map([[1, 3]]));
    expect(lines.map((l) => l.maxQty)).toEqual([0, 1]);
  });

  it('toggling a serial keeps quantity equal to the picks and never exceeds maxQty', () => {
    const [base] = invoiceItemsToSourceLines([sold], undefined, meta, undefined, [row()]);
    let line = { ...base, included: true };
    line = { ...line, ...toggleSerialPick(line, 'S1') };
    expect(line.quantity).toBe(1);
    line = { ...line, ...toggleSerialPick(line, 'S3') };
    expect(line.quantity).toBe(2);
    expect(pickedSerials(line)).toEqual(['S1', 'S3']);
    // maxQty is 2: a third pick is ignored.
    const capped = { ...line, ...toggleSerialPick({ ...line, soldSerialNumbers: ['S1', 'S3', 'S4'] }, 'S4') };
    expect(pickedSerials(capped)).toEqual(['S1', 'S3']);
    line = { ...line, ...toggleSerialPick(line, 'S1') };
    expect(line.quantity).toBe(1);
  });

  it('derives the payload quantity from the picked serials on pick-list lines', () => {
    const [base] = invoiceItemsToSourceLines([sold], undefined, meta, undefined, [row()]);
    const line = { ...base, included: true, quantity: 5, serialNumbersText: 'S1, S3' };
    expect(sourceLineReturnPayload(line)).toEqual(
      expect.objectContaining({ quantity: 2, serialNumbers: ['S1', 'S3'] }),
    );
  });

  it('trims free-text serials when the quantity shrinks', () => {
    expect(trimSerialsToQty('A, B, C', 2)).toBe('A, B');
    expect(trimSerialsToQty('A', 2)).toBe('A');
    expect(trimSerialsToQty(undefined, 1)).toBe('');
  });
});
