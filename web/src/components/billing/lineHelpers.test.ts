import { describe, expect, it } from 'vitest';
import { parseSerialInput, parseSerialNumbersText } from './lineHelpers';

describe('parseSerialInput — QOS-0035 bulk serial paste', () => {
  it('splits on commas and newlines, trimming blanks', () => {
    const parsed = parseSerialInput('SN-001, SN-002\nSN-003,,  \n');
    expect(parsed.serials).toEqual(['SN-001', 'SN-002', 'SN-003']);
    expect(parsed.duplicates).toEqual([]);
    expect(parsed.rangesExpanded).toBe(0);
  });

  it('expands a same-prefix numeric range, preserving zero-padding width', () => {
    const parsed = parseSerialInput('IMEI0998-IMEI1002');
    expect(parsed.serials).toEqual(['IMEI0998', 'IMEI0999', 'IMEI1000', 'IMEI1001', 'IMEI1002']);
    expect(parsed.rangesExpanded).toBe(1);
  });

  it('leaves a mismatched-prefix or non-numeric hyphenated token alone', () => {
    const parsed = parseSerialInput('ABC-100-XYZ-200, LOT-A');
    // 'ABC-100-XYZ-200' has more than one hyphen so it is not treated as a range.
    expect(parsed.serials).toEqual(['ABC-100-XYZ-200', 'LOT-A']);
    expect(parsed.rangesExpanded).toBe(0);
  });

  it('does not expand an inverted or absurdly large range', () => {
    expect(parseSerialInput('SN005-SN001').serials).toEqual(['SN005-SN001']);
    expect(parseSerialInput('SN00001-SN99999').serials).toEqual(['SN00001-SN99999']);
  });

  it('de-dupes repeated serials (a barcode scanned twice) and reports them', () => {
    const parsed = parseSerialInput('SN-1, SN-2, SN-1, SN-3, SN-2');
    expect(parsed.serials).toEqual(['SN-1', 'SN-2', 'SN-3']);
    expect(parsed.duplicates.sort()).toEqual(['SN-1', 'SN-2']);
  });

  it('de-dupes serials produced by an expanded range too', () => {
    // Range syntax needs exactly one hyphen in the token — a prefix that
    // itself contains a hyphen (e.g. "SN-001") is ambiguous and left as-is.
    const parsed = parseSerialInput('SN0001-SN0003, SN0002');
    expect(parsed.serials).toEqual(['SN0001', 'SN0002', 'SN0003']);
    expect(parsed.duplicates).toEqual(['SN0002']);
  });

  it('parseSerialNumbersText stays a thin wrapper returning just the serial list', () => {
    expect(parseSerialNumbersText('SN-1, SN-1')).toEqual(['SN-1']);
  });
});
