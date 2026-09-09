import { describe, expect, it } from 'vitest';
import type { LineItem } from '@/types/domain';
import {
  invoiceItemsToSourceLines,
  sourceLineReturnPayload,
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
    expect(lines[0].serialNumbersText).toBe('SN-1, SN-2');
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
