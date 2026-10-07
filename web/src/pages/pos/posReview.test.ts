import { afterEach, describe, expect, it, vi } from 'vitest';
import { mapRow } from '@/offline/posCatalog';
import { encodeEscPosReceipt } from '@/pages/pos/escposReceipt';
import { parseScaleReading } from '@/pages/pos/scaleReading';

function indexOfSequence(bytes: Uint8Array, seq: number[]): number {
  for (let i = 0; i <= bytes.length - seq.length; i += 1) {
    if (seq.every((value, offset) => bytes[i + offset] === value)) return i;
  }
  return -1;
}

describe('ESC/POS receipt image', () => {
  afterEach(() => vi.restoreAllMocks());

  it('prints the Hindi image before the cut, not after it', () => {
    const width = 384;
    const height = 28;
    const fakeCanvas = {
      width: 0,
      height: 0,
      getContext: () => ({
        fillStyle: '',
        font: '',
        fillRect: () => undefined,
        fillText: () => undefined,
        getImageData: () => ({ data: new Uint8ClampedArray(width * height * 4).fill(255) }),
      }),
    };
    vi.spyOn(document, 'createElement').mockReturnValue(fakeCanvas as unknown as HTMLElement);
    const bytes = encodeEscPosReceipt({
      number: 'INV-1',
      grandTotal: '10.00',
      items: [{ name: 'नमक', quantity: 1, lineTotal: '10.00' }],
      rasterLines: ['नमक'],
      pulseDrawer: true,
    });
    const image = indexOfSequence(bytes, [0x1d, 0x76, 0x30]);
    const cut = indexOfSequence(bytes, [0x1d, 0x56, 0x00]);
    expect(image).toBeGreaterThan(-1);
    expect(cut).toBeGreaterThan(image);
    expect(cut).toBe(bytes.length - 3);
  });

  it('still ends with the cut when there is no image', () => {
    const bytes = encodeEscPosReceipt({ number: 'INV-2', grandTotal: '5.00' });
    expect(Array.from(bytes.slice(-3))).toEqual([0x1d, 0x56, 0x00]);
  });
});

describe('offline catalogue rows', () => {
  it('reads the camelCase keys the API renderer sends', () => {
    const row = mapRow({ id: 1, name: 'Tablet', sku: 'T', trackBatch: true, trackSerial: true, productType: 'GOODS' });
    expect(row.trackBatch).toBe(true);
    expect(row.trackSerial).toBe(true);
    expect(row.productType).toBe('GOODS');
  });

  it('still reads snake_case keys', () => {
    const row = mapRow({ id: 2, name: 'Tablet', sku: 'T', track_batch: true, product_type: 'GOODS' });
    expect(row.trackBatch).toBe(true);
    expect(row.productType).toBe('GOODS');
  });
});

describe('scale line', () => {
  it('reads a stable weight and ignores an unstable one', () => {
    expect(parseScaleReading('ST,GS,  1.250 kg')).toEqual({ weight: 1.25, stable: true });
    expect(parseScaleReading('US,GS,  1.250 kg')?.stable).toBe(false);
  });
});
