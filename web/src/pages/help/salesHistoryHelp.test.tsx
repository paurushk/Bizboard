import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { getContextHelpPage } from '@/contextHelp/catalog';
import { FAQ_CATEGORIES, FAQ_ITEMS } from './faqContent';
import { HELP_INTENTS } from './intents';

function faqText(id: string): string {
  const item = FAQ_ITEMS.find((row) => row.id === id);
  expect(item, id).toBeTruthy();
  return render(<>{item!.answer}</>).container.textContent ?? '';
}

function pageText(id: string): { en: string; hi: string } {
  const page = getContextHelpPage(id);
  expect(page, id).toBeTruthy();
  const parts = [
    page!.summary,
    ...page!.howItWorks,
    ...page!.businessImpact,
    ...page!.keyRules,
    ...page!.commonMistakes,
    ...page!.nextActions,
  ];
  for (const part of parts) expect(part.hi?.trim(), part.en).toBeTruthy();
  return {
    en: parts.map((part) => part.en).join('\n'),
    hi: parts.map((part) => part.hi ?? '').join('\n'),
  };
}

const HISTORY_FAQS = FAQ_ITEMS.filter((item) => item.category === 'Sales history');

describe('sales history help', () => {
  it('has its own FAQ section next to sales invoices', () => {
    const at = FAQ_CATEGORIES.indexOf('Sales history');
    expect(FAQ_CATEGORIES[at - 1]).toBe('Sales invoices');
    expect(HISTORY_FAQS.length).toBeGreaterThanOrEqual(10);
  });

  it('every label in the Sales history answers resolves to screen text', () => {
    for (const item of HISTORY_FAQS) {
      const text = faqText(item.id);
      expect(text, item.id).not.toMatch(/\bt:|\b(history|common|status|sweep2|nav|invoiceDetail)\.[a-zA-Z]/);
    }
  });

  it('finding a bill names search, the customer box, dates, and Back', () => {
    const text = faqText('sales-history-find-bill');
    expect(text).toMatch(/Bill number, customer, or phone/);
    expect(text).toMatch(/2 letters/);
    expect(text).toMatch(/This FY/);
    expect(text).toMatch(/returned/);
    expect(text).toMatch(/Back/);
  });

  it('payment chips match the register buckets', () => {
    const text = faqText('sales-history-payment-chips');
    expect(text).toMatch(/credit note/);
    expect(text).toMatch(/settlement discount/);
    expect(text).toMatch(/due date has passed/);
    expect(text).toMatch(/Paid — receipt pending/);
  });

  it('bulk ZIP, CSV, and print answers carry the real limits', () => {
    const zip = faqText('sales-history-bulk-pdf');
    expect(zip).toMatch(/Download PDFs \(zip\)/);
    expect(zip).toMatch(/100 bills/);
    expect(zip).toMatch(/7 days/);
    expect(zip).toMatch(/dash/);
    expect(zip).toMatch(/only by the person who made it/);

    const csv = faqText('sales-history-export-csv');
    expect(csv).toMatch(/Export CSV/);
    expect(csv).toMatch(/5,000/);
    expect(csv).toMatch(/Cancel reason/);

    const print = faqText('sales-history-print');
    expect(print).toMatch(/80/);
    expect(print).toMatch(/58/);
    expect(print).toMatch(/Retry/);
  });

  it('cancel answers cover the reason, the second Owner, and what blocks it', () => {
    const approval = faqText('sales-history-cancel-approval');
    expect(approval).toMatch(/second Owner/);
    expect(approval).toMatch(/only Owner/);
    expect(approval).toMatch(/Cancel pending/);
    expect(approval).toMatch(/72 hours/);

    const refused = faqText('sales-history-cancel-refused');
    expect(refused).toMatch(/IRN/);
    expect(refused).toMatch(/Open receipts/);

    const cancel = faqText('cancel-invoice');
    expect(cancel).toMatch(/reason/);
    expect(cancel).toMatch(/second Owner/);

    const edit = faqText('edit-completed-invoice');
    expect(edit).toMatch(/Amend/);
    expect(edit).toMatch(/Owner/);
  });

  it('payment and row-menu answers name the permissions', () => {
    const pay = faqText('sales-history-record-payment');
    expect(pay).toMatch(/Record payment/);
    expect(pay).toMatch(/Partial/);
    expect(pay).toMatch(/GST does not change/);

    const menu = faqText('sales-history-row-actions');
    expect(menu).toMatch(/Profit Details/);
    expect(menu).toMatch(/financial reports/);
    expect(menu).toMatch(/waiting for approval/);
  });

  it('the screen tip covers search, buckets, bulk, cancel approval, and amend in both languages', () => {
    const { en, hi } = pageText('sales-history');
    expect(en).toMatch(/phone/);
    expect(en).toMatch(/Overdue/);
    expect(en).toMatch(/5,000/);
    expect(en).toMatch(/100 bills/);
    expect(en).toMatch(/second Owner/);
    expect(en).toMatch(/72 hours/);
    expect(en).toMatch(/Amend/);
    expect(hi).toMatch(/Owner/);
    expect(hi).toMatch(/72 घंटे/);
    expect(hi).toMatch(/Overdue/);
  });

  it('the completed-bill answer points to Amend and the cancel approval', () => {
    const intent = HELP_INTENTS.find((row) => row.intentId === 'edit-completed-invoice')!;
    expect(intent.action?.en).toMatch(/history\.amend/);
    expect(intent.action?.en).toMatch(/second Owner/);
    expect(intent.action?.hi).toMatch(/दूसरे Owner/);
  });
});
