import { describe, expect, it } from 'vitest';
import { csvCell, csvSafe, toCsv } from '@/utils/csv';

describe('csv formula-injection guard (F3-001)', () => {
  it('prefixes formula-leading values with a quote', () => {
    expect(csvSafe('=1+1')).toBe("'=1+1");
    expect(csvSafe('+SUM(A1)')).toBe("'+SUM(A1)");
    expect(csvSafe('@foo')).toBe("'@foo");
    expect(csvSafe('=cmd|\' /C calc\'!A0')).toBe("'=cmd|' /C calc'!A0");
  });

  it('guards tab / CR / LF leads', () => {
    expect(csvSafe('\t=1')).toBe("'\t=1");
    expect(csvSafe('\r=1')).toBe("'\r=1");
    expect(csvSafe('\n=1+1')).toBe("'\n=1+1");
  });

  it('guards a formula hidden behind leading whitespace', () => {
    expect(csvSafe('   =1+1')).toBe("'   =1+1");
  });

  it('leaves plain text and numeric-looking negatives untouched', () => {
    expect(csvSafe('Nuts & Bolts Pvt Ltd')).toBe('Nuts & Bolts Pvt Ltd');
    expect(csvSafe('-42.5')).toBe('-42.5');
    expect(csvSafe('-1,250.00')).toBe('-1,250.00');
    expect(csvSafe('')).toBe('');
    expect(csvSafe(null)).toBe('');
    expect(csvSafe(undefined)).toBe('');
  });

  it('quotes negative non-numbers (e.g. "-cmd")', () => {
    expect(csvSafe('-cmd|calc')).toBe("'-cmd|calc");
  });

  it('csvCell quotes and doubles inner quotes', () => {
    expect(csvCell('a "b" c')).toBe('"a ""b"" c"');
    expect(csvCell('=1')).toBe('"\'=1"');
  });

  it('toCsv joins rows with CRLF', () => {
    expect(toCsv([['Name', 'Qty'], ['=HYPERLINK("x")', 5]])).toBe(
      '"Name","Qty"\r\n"\'=HYPERLINK(""x"")","5"',
    );
  });
});
