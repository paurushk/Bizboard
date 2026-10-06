import { describe, expect, it } from 'vitest';
import { isScannerBurst, parseQtyBarcode } from './scanInput';

describe('scanInput', () => {
  it('BUG-UI-002 treats sub-50ms gaps as a scanner and slower typing as a person', () => {
    expect(isScannerBurst([12, 18, 20])).toBe(true);
    expect(isScannerBurst([12, 80])).toBe(false);
  });

  it('BUG-UI-003 reads a quantity prefix', () => {
    expect(parseQtyBarcode('5*8901030383')).toEqual({ quantity: 5, code: '8901030383' });
    expect(parseQtyBarcode('8901030383')).toBeNull();
  });
});
