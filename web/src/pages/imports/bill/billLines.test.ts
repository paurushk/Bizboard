import { describe, expect, it } from 'vitest';
import type { PurchaseBillPreview } from '@/types/domain';
import {
  billedFromPack,
  errorFor,
  hasPackData,
  isBillPreview,
  isLineComplete,
  lineAmount,
  linePayload,
  lineSignature,
  localLineErrors,
  newClientKey,
  payloadHash,
  toEditorLines,
  type EditorLine,
} from './billLines';

function line(over: Partial<EditorLine> = {}): EditorLine {
  return {
    clientKey: 'k1',
    lineId: 1,
    name: 'Soap',
    quantity: '2',
    unitPrice: '100',
    gstRate: '18',
    hsnCode: '3401',
    include: true,
    ...over,
  };
}

const codes = (l: EditorLine) => localLineErrors(l).map((e) => e.code);

describe('toEditorLines', () => {
  const preview = (lines: unknown[]) => ({ lines }) as unknown as PurchaseBillPreview;

  it('keeps unread fields blank instead of inventing a quantity or a GST rate', () => {
    const [row] = toEditorLines(preview([{ name: 'Blurry', lineId: 7, quantity: '', gstRate: '' }]));
    expect(row.quantity).toBe('');
    expect(row.gstRate).toBe('');
    expect(row.unitPrice).toBe('');
    expect(row.include).toBe(true);
  });

  it('reads camelCase and snake_case, and uses the server line id as the row key', () => {
    const rows = toEditorLines(
      preview([
        { lineId: 3, name: 'A', hsn_code: '3402', unit_price: '50', gst_rate: '12' },
        { lineId: 4, name: 'B', hsnCode: '3305', unitPrice: '60', gstRate: '5' },
      ]),
    );
    expect(rows[0]).toMatchObject({ clientKey: 'line-3', hsnCode: '3402', unitPrice: '50', gstRate: '12' });
    expect(rows[1]).toMatchObject({ clientKey: 'line-4', hsnCode: '3305', unitPrice: '60', gstRate: '5' });
  });

  it('gives a row without a server id its own key', () => {
    const rows = toEditorLines(preview([{ name: 'A' }, { name: 'B' }]));
    expect(rows[0].clientKey).not.toBe(rows[1].clientKey);
    expect(rows[0].lineId).toBeUndefined();
  });

  it('keeps an unticked row unticked and takes the row position only when it has four numbers', () => {
    const rows = toEditorLines(
      preview([
        { lineId: 1, name: 'A', include: false, bbox: [0.1, 0.2, 0.3, 0.4] },
        { lineId: 2, name: 'B', bbox: [0.1, 0.2] },
      ]),
    );
    expect(rows[0].include).toBe(false);
    expect(rows[0].bbox).toEqual([0.1, 0.2, 0.3, 0.4]);
    expect(rows[1].bbox).toBeNull();
  });

  it('returns nothing for a missing preview', () => {
    expect(toEditorLines(null)).toEqual([]);
  });
});

describe('isBillPreview', () => {
  it('is true only for an object with a lines array', () => {
    expect(isBillPreview({ lines: [] } as never)).toBe(true);
    expect(isBillPreview([] as never)).toBe(false);
    expect(isBillPreview(null as never)).toBe(false);
  });
});

describe('localLineErrors', () => {
  it('accepts a complete row', () => {
    expect(localLineErrors(line())).toEqual([]);
    expect(isLineComplete(line())).toBe(true);
  });

  it('flags each missing or wrong field with its own code', () => {
    expect(codes(line({ name: '  ' }))).toEqual(['NAME_REQUIRED']);
    expect(codes(line({ quantity: '' }))).toEqual(['QTY_POSITIVE']);
    expect(codes(line({ quantity: '0' }))).toEqual(['QTY_POSITIVE']);
    expect(codes(line({ unitPrice: '' }))).toEqual(['PRICE_NUMBER']);
    expect(codes(line({ unitPrice: '-5' }))).toEqual(['PRICE_NUMBER']);
    expect(codes(line({ gstRate: '' }))).toEqual(['GST_REQUIRED']);
    expect(codes(line({ gstRate: '7' }))).toEqual(['GST_SLAB']);
    expect(isLineComplete(line({ gstRate: '' }))).toBe(false);
  });

  it('accepts a free item priced at zero', () => {
    expect(localLineErrors(line({ unitPrice: '0' }))).toEqual([]);
  });

  it('accepts HSN of 2, 4, 6 or 8 digits and blank, and refuses the rest', () => {
    for (const hsn of ['', '34', '3401', '340111', '34011100']) {
      expect(localLineErrors(line({ hsnCode: hsn })), hsn).toEqual([]);
    }
    for (const hsn of ['3', '123', '12345', 'AB12', '3401 1']) {
      expect(codes(line({ hsnCode: hsn })), hsn).toEqual(['HSN_FORMAT']);
    }
  });

  it('reports several problems on one row together', () => {
    expect(codes(line({ name: '', gstRate: '', hsnCode: '123' }))).toEqual([
      'NAME_REQUIRED',
      'GST_REQUIRED',
      'HSN_FORMAT',
    ]);
  });
});

describe('errorFor', () => {
  it('finds a blocking error for a field and ignores warnings', () => {
    const errors = [
      { field: 'gst_rate', code: 'X', message: 'warn', severity: 'warning' as const },
      { field: 'hsn_code', code: 'HSN_FORMAT', message: 'bad' },
    ];
    expect(errorFor(errors, 'gst_rate')).toBeUndefined();
    expect(errorFor(errors, 'hsn_code')?.code).toBe('HSN_FORMAT');
    expect(errorFor(undefined, 'hsn_code')).toBeUndefined();
  });
});

describe('linePayload and lineSignature', () => {
  it('sends an existing row by its id and a new row as new', () => {
    expect(linePayload(line({ lineId: 9 }))).toMatchObject({ lineId: 9, name: 'Soap', include: true });
    expect(linePayload(line({ lineId: 9 })).isNew).toBeUndefined();
    const fresh = linePayload(line({ lineId: undefined }));
    expect(fresh.isNew).toBe(true);
    expect(fresh.lineId).toBeUndefined();
  });

  it('defaults optional fields so the server never receives undefined', () => {
    const body = linePayload(line({ sku: undefined, mrp: undefined, discountPercent: undefined, productId: undefined }));
    expect(body).toMatchObject({ sku: '', mrp: '0', discountPercent: '', productId: null, createNew: false });
  });

  it('changes the signature when an editable field changes, not when server fields do', () => {
    const base = lineSignature(line());
    expect(lineSignature(line({ quantity: '3' }))).not.toBe(base);
    expect(lineSignature(line({ include: false }))).not.toBe(base);
    expect(lineSignature(line({ productId: 5 }))).not.toBe(base);
    expect(lineSignature(line({ errors: [{ field: 'x', code: 'Y', message: 'z' }], flags: ['f'] }))).toBe(base);
  });
});

describe('hasPackData and billedFromPack', () => {
  it('shows pack columns only when a row has cases or units per case', () => {
    expect(hasPackData([line(), line({ pcs: '10' })])).toBe(false);
    expect(hasPackData([line(), line({ cs: '2' })])).toBe(true);
    expect(hasPackData([line({ upc: '12' })])).toBe(true);
    expect(hasPackData([line({ cs: '  ' })])).toBe(false);
  });

  it('computes cases x units + loose pieces, and gives up without a usable units-per-case', () => {
    expect(billedFromPack('2', '3', '12')).toBe('27');
    expect(billedFromPack('', '5', '10')).toBe('5');
    expect(billedFromPack('2', '3', '')).toBeNull();
    expect(billedFromPack('2', '3', '0')).toBeNull();
    expect(billedFromPack('x', '3', '12')).toBeNull();
  });
});

describe('payloadHash', () => {
  it('is stable for equal payloads and differs when anything changes', () => {
    const a = { billNumber: 'A', lines: [{ lineId: 1, name: 'x' }] };
    expect(payloadHash(a)).toBe(payloadHash({ billNumber: 'A', lines: [{ lineId: 1, name: 'x' }] }));
    expect(payloadHash(a)).not.toBe(payloadHash({ billNumber: 'B', lines: [{ lineId: 1, name: 'x' }] }));
    expect(payloadHash(a)).toMatch(/^[0-9a-z]+$/);
  });
});

describe('lineAmount', () => {
  it('adds GST to a tax-exclusive price and applies the line discount first', () => {
    expect(lineAmount(line())).toBe(236);
    expect(lineAmount(line({ discountPercent: '10' }))).toBe(212.4);
  });

  it('treats a tax-inclusive price as already containing GST', () => {
    expect(lineAmount(line({ unitPrice: '118' }), true)).toBe(236);
    expect(lineAmount(line({ unitPrice: '118', discountPercent: '10' }), true)).toBe(212.4);
  });

  it('is null until quantity and price are both numbers', () => {
    expect(lineAmount(line({ quantity: '' }))).toBeNull();
    expect(lineAmount(line({ unitPrice: 'abc' }))).toBeNull();
  });
});

describe('newClientKey', () => {
  it('never repeats', () => {
    expect(new Set(Array.from({ length: 50 }, () => newClientKey())).size).toBe(50);
  });
});
