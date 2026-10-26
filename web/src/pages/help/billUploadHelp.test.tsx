import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { resolveContextHelpPage } from '@/contextHelp';
import { getContextHelpPage } from '@/contextHelp/catalog';
import { FAQ_ITEMS } from './faqContent';

function faqText(id: string): string {
  const item = FAQ_ITEMS.find((row) => row.id === id);
  expect(item, id).toBeTruthy();
  return render(<>{item!.answer}</>).container.textContent ?? '';
}

const SALES_FAQS = [
  'upload-sales-bill',
  'upload-sales-bill-review',
  'upload-sales-bill-cannot-create',
  'upload-sales-bill-customer',
  'upload-sales-bill-products',
  'upload-sales-bill-price-list',
  'upload-sales-bill-totals',
  'upload-sales-bill-resume',
  'upload-sales-bill-csv',
  'upload-sales-bill-undo',
  'upload-sales-bill-ai-privacy',
  'upload-sales-bill-wrong-screen',
  'upload-sales-bill-gstin',
  'upload-sales-bill-duplicate',
];
const PURCHASE_FAQS = [
  'upload-purchase-bill',
  'upload-purchase-bill-review',
  'upload-purchase-bill-duplicate-nongst',
];

describe('bill upload help pages', () => {
  it('are shown on the upload routes', () => {
    expect(resolveContextHelpPage('/sales/bill-upload')).toBe('sales-bill-upload');
    expect(resolveContextHelpPage('/purchases/bill-upload')).toBe('purchase-bill-upload');
  });

  for (const id of ['sales-bill-upload', 'purchase-bill-upload']) {
    describe(id, () => {
      const page = getContextHelpPage(id);

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

      it('walks through the whole flow, not just one sentence', () => {
        expect(page!.howItWorks.length).toBeGreaterThanOrEqual(5);
        expect(page!.keyRules.length).toBeGreaterThanOrEqual(3);
      });
    });
  }

  it('the sales page covers review, matching, prices, totals, products and undo', () => {
    const page = getContextHelpPage('sales-bill-upload')!;
    const en = [...page.howItWorks, ...page.businessImpact, ...page.keyRules, ...page.commonMistakes]
      .map((part) => part.en)
      .join('\n');
    expect(en).toMatch(/original bill/);
    expect(en).toMatch(/never dropped silently/);
    expect(en).toMatch(/exact GSTIN or name/);
    expect(en).toMatch(/Owner or Manager/);
    expect(en).toMatch(/needs review/);
    expect(en).toMatch(/undo the whole import/);
    expect(en).toMatch(/prices include GST/i);
    expect(en).toMatch(/Import permission and the right to create sales invoices/);
  });

  it('the purchase page covers duplicates, Non-GST and reverse charge', () => {
    const page = getContextHelpPage('purchase-bill-upload')!;
    const en = [...page.howItWorks, ...page.businessImpact, ...page.keyRules].map((part) => part.en).join('\n');
    expect(en).toMatch(/same number and date/);
    expect(en).toMatch(/Non-GST/);
    expect(en).toMatch(/reverse-charge/);
  });

  it('links to the products that need review', () => {
    for (const id of ['sales-bill-upload', 'purchase-bill-upload']) {
      const paths = getContextHelpPage(id)!.relatedPages.map((p) => p.path);
      expect(paths, id).toContain('/inventory/products?needsReview=1');
    }
  });
});

describe('bill upload FAQs', () => {
  it('exist, under the right headings, with search keywords', () => {
    for (const id of SALES_FAQS) {
      const item = FAQ_ITEMS.find((row) => row.id === id);
      expect(item, id).toBeTruthy();
      expect(item!.category, id).toBe('Sales invoices');
      expect((item!.keywords ?? []).length, id).toBeGreaterThanOrEqual(3);
    }
    for (const id of PURCHASE_FAQS) {
      const item = FAQ_ITEMS.find((row) => row.id === id);
      expect(item, id).toBeTruthy();
      expect(item!.category, id).toBe('Purchases & ITC');
    }
  });

  it('answer the questions people will actually ask', () => {
    expect(faqText('upload-sales-bill')).toMatch(/never completes the bill/);
    expect(faqText('upload-sales-bill')).toMatch(/Import permission/);
    expect(faqText('upload-sales-bill-cannot-create')).toMatch(/every problem is listed together/);
    expect(faqText('upload-sales-bill-cannot-create')).toMatch(/2, 4, 6 or 8 digits/);
    expect(faqText('upload-sales-bill-customer')).toMatch(/exactly/);
    expect(faqText('upload-sales-bill-products')).toMatch(/needs review/);
    expect(faqText('upload-sales-bill-price-list')).toMatch(/Owner or Manager/);
    expect(faqText('upload-sales-bill-totals')).toMatch(/same tax engine/);
    expect(faqText('upload-sales-bill-resume')).toMatch(/Recent uploads/);
    expect(faqText('upload-sales-bill-csv')).toMatch(/no AI/);
    expect(faqText('upload-sales-bill-undo')).toMatch(/still a draft/);
    expect(faqText('upload-sales-bill-ai-privacy')).toMatch(/third-party AI service/);
    expect(faqText('upload-sales-bill-wrong-screen')).toMatch(/Switch to a purchase bill/);
    expect(faqText('upload-sales-bill-gstin')).toMatch(/one character/);
    expect(faqText('upload-sales-bill-duplicate')).toMatch(/not a duplicate/);
    expect(faqText('upload-purchase-bill-duplicate-nongst')).toMatch(/Non-GST/);
  });

  it('can be found by the words people type', () => {
    const find = (word: string) =>
      FAQ_ITEMS.filter((item) =>
        [item.question, ...(item.keywords ?? [])].join(' ').toLowerCase().includes(word),
      ).map((item) => item.id);
    expect(find('duplicate product')).toContain('upload-sales-bill-products');
    expect(find('price list')).toContain('upload-sales-bill-price-list');
    expect(find('lost upload')).toContain('upload-sales-bill-resume');
    expect(find('undo import')).toContain('upload-sales-bill-undo');
    expect(find('excel')).toContain('upload-sales-bill-csv');
  });
});
