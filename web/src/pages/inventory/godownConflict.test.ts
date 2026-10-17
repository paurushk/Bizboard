import { describe, expect, it } from 'vitest';
import {
  applyConflictChoice,
  parseStockCountConflicts,
  parseStockCountLinesChanged,
  resolutionsFor,
} from './godownConflict';

describe('godown conflict (C-01)', () => {
  it('parses 409 STOCK_COUNT_CONFLICT rows', () => {
    const err = {
      response: {
        status: 409,
        data: {
          success: false,
          error: {
            code: 'STOCK_COUNT_CONFLICT',
            details: {
              conflicts: [
                {
                  lineId: 3,
                  productName: 'Rice',
                  serverQty: '12',
                  localQty: '10',
                  snapshotQty: '8',
                },
              ],
            },
          },
        },
      },
    };
    const rows = parseStockCountConflicts(err);
    expect(rows).toHaveLength(1);
    expect(rows?.[0]?.serverQty).toBe('12');
    expect(rows?.[0]?.localQty).toBe('10');
  });

  it('Keep server vs Keep local is an explicit choice', () => {
    const conflicts = [
      { lineId: 1, productName: 'A', serverQty: '5', localQty: '4', snapshotQty: '3' },
    ];
    expect(applyConflictChoice(conflicts, 'KEEP_SERVER').resolve).toBe('KEEP_SERVER');
    expect(applyConflictChoice(conflicts, 'KEEP_LOCAL').resolve).toBe('KEEP_LOCAL');
  });

  it('gives every conflicted line the same answer when asked to', () => {
    const conflicts = [
      { lineId: 1, productName: 'A', serverQty: '5', localQty: '4', snapshotQty: '3' },
      { lineId: 2, productName: 'B', serverQty: '6', localQty: '4', snapshotQty: '3' },
    ];
    expect(resolutionsFor(conflicts, 'ADJUST_FOR_MOVEMENTS')).toEqual({
      1: 'ADJUST_FOR_MOVEMENTS',
      2: 'ADJUST_FOR_MOVEMENTS',
    });
  });

  it('parses the lines another counter changed (409 STOCK_COUNT_LINE_CHANGED)', () => {
    const err = {
      response: {
        status: 409,
        data: {
          error: {
            code: 'STOCK_COUNT_LINE_CHANGED',
            details: { lines: [{ line_id: 4, product_name: 'Tea', counted_qty: '6', version: 2 }] },
          },
        },
      },
    };
    expect(parseStockCountLinesChanged(err)).toEqual([{ lineId: 4, productName: 'Tea', countedQty: '6', version: 2 }]);
    expect(parseStockCountConflicts(err)).toBeNull();
  });
});
