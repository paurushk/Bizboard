import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { getContextHelpPage, resolveContextHelpPage } from '@/contextHelp';
import { FAQ_ITEMS } from './faqContent';

function faqText(id: string): string {
  const item = FAQ_ITEMS.find((row) => row.id === id);
  expect(item, id).toBeTruthy();
  return render(<>{item!.answer}</>).container.textContent ?? '';
}

const RETURN_FAQS = [
  'sales-return',
  'sales-return-partial-or-full',
  'sales-return-damaged-goods',
  'sales-return-which-lot',
  'sales-return-credit-note',
  'sales-return-more-than-owed',
  'sales-return-who-can',
  'sales-return-blocked',
  'sales-return-find',
];

describe('sales returns help page', () => {
  const page = getContextHelpPage('sales-returns')!;

  it('is shown on the sales returns route', () => {
    expect(resolveContextHelpPage('/sales/returns')).toBe('sales-returns');
  });

  it('has a Hindi line for every section it shows', () => {
    const parts = [
      page.summary,
      ...page.howItWorks,
      ...page.businessImpact,
      ...page.keyRules,
      ...page.commonMistakes,
      ...page.nextActions,
    ];
    for (const part of parts) expect(part.hi?.trim(), part.en).toBeTruthy();
  });

  it('covers condition, lots, GST Guard, search, dates and status changes', () => {
    const en = [...page.howItWorks, ...page.keyRules, ...page.commonMistakes].map((p) => p.en).join('\n');
    expect(en).toMatch(/Damaged items are written off/);
    expect(en).toMatch(/same lot and at the same cost/);
    expect(en).toMatch(/Owner or Manager can override/);
    expect(en).toMatch(/From \/ To dates/);
    expect(en).toMatch(/cannot be earlier than the invoice date/);
    expect(en).toMatch(/invoice shows Returned/);
    expect(en).toMatch(/unallocated customer advance/);
  });

  it('links to credit notes, history, stock and purchase returns', () => {
    const paths = page.relatedPages.map((p) => p.path);
    expect(paths).toEqual(
      expect.arrayContaining(['/sales/history', '/sales/credit-notes', '/purchases/returns', '/inventory/stock']),
    );
  });
});

describe('sales returns FAQs', () => {
  it('exist under Returns & notes with search keywords', () => {
    for (const id of RETURN_FAQS) {
      const item = FAQ_ITEMS.find((row) => row.id === id);
      expect(item, id).toBeTruthy();
      expect(item!.category, id).toBe('Returns & notes');
      expect((item!.keywords ?? []).length, id).toBeGreaterThanOrEqual(3);
    }
  });

  it('have unique ids', () => {
    const ids = FAQ_ITEMS.map((row) => row.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it('answer the questions people will actually ask', () => {
    expect(faqText('sales-return-partial-or-full')).toMatch(/leaves the invoice Completed/);
    expect(faqText('sales-return-partial-or-full')).toMatch(/Returned/);
    expect(faqText('sales-return-damaged-goods')).toMatch(/written off/);
    expect(faqText('sales-return-which-lot')).toMatch(/same lot/);
    expect(faqText('sales-return-which-lot')).toMatch(/serials already returned/i);
    expect(faqText('sales-return-credit-note')).toMatch(/automatically issues a linked GST credit note/);
    expect(faqText('sales-return-more-than-owed')).toMatch(/customer advance/);
    expect(faqText('sales-return-who-can')).toMatch(/draft/);
    expect(faqText('sales-return-blocked')).toMatch(/GST Guard/);
    expect(faqText('sales-return-blocked')).toMatch(/Owner or Manager/);
    expect(faqText('sales-return-find')).toMatch(/From and To dates/);
  });

  it('can be found by the words people type', () => {
    const find = (word: string) =>
      FAQ_ITEMS.filter((item) =>
        [item.question, ...(item.keywords ?? [])].join(' ').toLowerCase().includes(word),
      ).map((item) => item.id);
    expect(find('partial return')).toContain('sales-return-partial-or-full');
    expect(find('damaged')).toContain('sales-return-damaged-goods');
    expect(find('fifo')).toContain('sales-return-which-lot');
    expect(find('refund')).toContain('sales-return-more-than-owed');
    expect(find('gst guard')).toContain('sales-return-blocked');
    expect(find('search return')).toContain('sales-return-find');
  });
});
