import { describe, expect, it } from 'vitest';
import { parseWeightedBarcode } from '@/pages/pos/weightedBarcode';
import { parseScaleReading } from '@/pages/pos/scaleReading';
import { cashNeedsOpenShift } from '@/pages/pos/posTerminal';
import { catalogSellBlocked } from '@/offline/posCatalog';
import { rasterCommand } from '@/pages/pos/escposRaster';
import { offlineTenderAllowed } from '@/pages/pos/posRules';

describe('POS plan helpers', () => {
  it('parses a weight barcode only when a rule is set', () => {
    expect(parseWeightedBarcode('2100015002501', null)).toBeNull();
    const hit = parseWeightedBarcode('2100015012500', {
      prefix: '21',
      type: 'weight',
      itemDigits: 5,
      valueDigits: 5,
      decimals: 3,
    });
    expect(hit).toEqual({ itemCode: '00015', weight: 1.25 });
  });

  it('treats an unstable scale line as not ready', () => {
    expect(parseScaleReading('ST, 1.250 kg')?.stable).toBe(true);
    expect(parseScaleReading('US, 1.250 kg')?.stable).toBe(false);
  });

  it('requires an open shift only when the company asks', () => {
    expect(cashNeedsOpenShift(false, null)).toBe(false);
    expect(cashNeedsOpenShift(true, 'OPEN')).toBe(false);
    expect(cashNeedsOpenShift(true, 'CLOSED')).toBe(true);
  });

  it('blocks a catalogue after 72 hours and keeps offline credit opt-in', () => {
    expect(catalogSellBlocked(71)).toBe(false);
    expect(catalogSellBlocked(72)).toBe(true);
    expect(offlineTenderAllowed('CREDIT')).toBe(false);
    expect(offlineTenderAllowed('CREDIT', { offlineCredit: true, namedCustomer: true })).toBe(true);
  });

  it('sets a bit in the raster for a dark pixel', () => {
    const rgba = new Uint8ClampedArray([0, 0, 0, 255, 255, 255, 255, 255]);
    const bytes = rasterCommand(2, 1, rgba);
    expect(bytes[0]).toBe(0x1d);
    expect(bytes[8] & 0x80).toBe(0x80);
  });
});
