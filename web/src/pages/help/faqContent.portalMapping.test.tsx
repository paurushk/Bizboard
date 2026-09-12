import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { FAQ_ITEMS } from './faqContent';

/**
 * QOS-0041 — the GSTR worksheets are calculation aids the user files themselves
 * (KNOWN LIMITATION C1). There must be contextual help that maps each worksheet
 * section to its GST-portal counterpart, or a less-experienced filer is stuck.
 */
describe('GSTR portal-mapping help (QOS-0041)', () => {
  it('has a GSTR-1 and a GSTR-3B "how to file on the portal" entry', () => {
    const ids = FAQ_ITEMS.map((f) => f.id);
    expect(ids).toContain('gstr1-portal-mapping');
    expect(ids).toContain('gstr3b-portal-mapping');
  });

  it('the GSTR-1 entry names the portal tables for every worksheet section', () => {
    const item = FAQ_ITEMS.find((f) => f.id === 'gstr1-portal-mapping')!;
    const text = render(<>{item.answer}</>).container.textContent ?? '';
    for (const section of ['B2B', 'B2CS', 'CDNR', 'HSN']) {
      expect(text, `GSTR-1 help missing a portal mapping for ${section}`).toContain(section);
    }
    expect(text.toLowerCase()).toContain('gst.gov.in');
  });

  it('the GSTR-3B entry maps the 3.1 / 4 tables and the filing steps', () => {
    const item = FAQ_ITEMS.find((f) => f.id === 'gstr3b-portal-mapping')!;
    const text = render(<>{item.answer}</>).container.textContent ?? '';
    expect(text).toContain('3.1');
    expect(text).toContain('table 4');
    expect(text.toLowerCase()).toMatch(/proceed to payment|offset|file with dsc/i);
  });
});
