import { describe, expect, it } from 'vitest';
import { getContextHelpPage } from '@/contextHelp';
import { FAQ_ITEMS } from '@/pages/help/faqContent';

const RECEIPT_FAQS = [
  'receipt-customer-tds',
  'receipt-settlement-discount',
  'receipt-refund-advance',
  'receipt-void-or-edit',
  'receipt-walk-in-advance',
  'receipt-cheque-clearing',
  'receipt-cash-269st',
  'receipt-bulk-apply-send',
  'receipt-offline',
  'receipt-export-voucher',
];

describe('receipts help', () => {
  it('has an English and a Hindi line for every point on the page help', () => {
    const page = getContextHelpPage('receipts');
    expect(page).toBeTruthy();
    for (const list of [page!.howItWorks, page!.keyRules, page!.commonMistakes]) {
      for (const { en, hi } of list) {
        expect(en.trim().length).toBeGreaterThan(10);
        expect((hi ?? '').trim().length).toBeGreaterThan(10);
      }
    }
  });

  it('answers the Money In questions in the FAQ, each with an id used once', () => {
    const ids = FAQ_ITEMS.map((f) => f.id);
    for (const id of RECEIPT_FAQS) expect(ids.filter((x) => x === id)).toHaveLength(1);
  });
});
