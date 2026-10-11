import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { getContextHelpPage, resolveContextHelpPage } from '@/contextHelp';
import { FAQ_ITEMS } from './faqContent';

function faqText(id: string): string {
  const item = FAQ_ITEMS.find((row) => row.id === id);
  expect(item, id).toBeTruthy();
  return render(<>{item!.answer}</>).container.textContent ?? '';
}

const QUOTATION_FAQS = [
  'quotation-convert',
  'quotation-partial-close',
  'quotation-create-edit',
  'quotation-share',
  'quotation-duplicate',
  'quotation-expiry',
  'quotation-return-quantity',
  'quotation-source-link',
];

describe('quotation help page', () => {
  const page = getContextHelpPage('quotations');

  it('is shown on every quotation route, including the editor', () => {
    for (const path of ['/sales/quotations', '/sales/quotations/new', '/sales/quotations/12/edit']) {
      expect(resolveContextHelpPage(path), path).toBe('quotations');
    }
  });

  it('has a Hindi line for every section it shows', () => {
    expect(page).toBeTruthy();
    const parts = [
      page!.summary,
      ...page!.howItWorks,
      ...page!.businessImpact,
      ...page!.keyRules,
      ...page!.commonMistakes,
      ...page!.nextActions,
    ];
    for (const part of parts) expect(part.hi?.trim(), part.en).toBeTruthy();
  });

  it('explains sharing, duplicating, closing and the lifecycle', () => {
    const en = [...page!.howItWorks, ...page!.keyRules].map((part) => part.en).join('\n');
    expect(en).toMatch(/Share/);
    expect(en).toMatch(/Duplicate/);
    expect(en).toMatch(/Close remaining/);
    expect(en).toMatch(/lifecycle/);
    expect(en).toMatch(/shared across the documents by value/);
    expect(en).toMatch(/a paisa/);
  });

  it('says that quantity comes back when a draft is deleted or cancelled', () => {
    const en = page!.businessImpact.map((part) => part.en).join('\n');
    expect(en).toMatch(/gives the converted quantity back/);
  });
});

describe('quotation FAQs', () => {
  it('all exist, in the quotations category, with no unresolved labels', () => {
    for (const id of QUOTATION_FAQS) {
      const item = FAQ_ITEMS.find((row) => row.id === id);
      expect(item, id).toBeTruthy();
      expect(item!.category).toBe('Quotations, orders & challans');
      expect(faqText(id), id).not.toMatch(/\bt:|\b(nav|common|history)\.[a-zA-Z]/);
    }
  });

  it('ids are unique', () => {
    const ids = FAQ_ITEMS.map((item) => item.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it('sharing names the public link, revocation, expiry and Sent', () => {
    const text = faqText('quotation-share');
    expect(text).toMatch(/public PDF link/);
    expect(text).toMatch(/revoke/);
    expect(text).toMatch(/expired/);
    expect(text).toMatch(/Sent/);
  });

  it('duplicate leaves the original unchanged', () => {
    expect(faqText('quotation-duplicate')).toMatch(/original is not changed/);
  });

  it('expiry says there is no separate status and that converting needs a confirm', () => {
    const text = faqText('quotation-expiry');
    expect(text).toMatch(/no separate Expired status/);
    expect(text).toMatch(/after you confirm/);
  });

  it('returned quantity separates orders from invoices', () => {
    const text = faqText('quotation-return-quantity');
    expect(text).toMatch(/never returns quantity/);
    expect(text).toMatch(/nightly/);
  });

  it('close remaining and numbering gaps are covered', () => {
    const text = faqText('quotation-partial-close');
    expect(text).toMatch(/Close remaining/);
    expect(text).toMatch(/gap in the numbers/);
  });

  it('a search for share or duplicate finds its answer', () => {
    const find = (word: string) =>
      FAQ_ITEMS.filter((item) => item.keywords.some((k) => k.includes(word))).map((item) => item.id);
    expect(find('whatsapp quotation')).toContain('quotation-share');
    expect(find('duplicate quotation')).toContain('quotation-duplicate');
    expect(find('release quantity')).toContain('quotation-return-quantity');
  });
});
