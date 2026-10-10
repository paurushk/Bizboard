import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { getContextHelpPage } from '@/contextHelp/catalog';
import { FAQ_ITEMS } from './faqContent';
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
  return {
    en: parts.map((part) => part.en).join('\n'),
    hi: parts.map((part) => part.hi ?? '').join('\n'),
  };
}

describe('sales invoice help', () => {
  it('the create-invoice tip covers preview, cash change, and stock that does not track', () => {
    const { en, hi } = pageText('sales-invoice');
    expect(en).toMatch(/Preview Mode/);
    expect(en).toMatch(/amount in words/i);
    expect(en).toMatch(/only cash/i);
    expect(en).toMatch(/Services/);
    expect(en).toMatch(/books on/i);
    expect(hi).toMatch(/Preview Mode/);
    expect(hi).toMatch(/नकद/);
  });

  it('the invoice detail tip covers the public link, e-invoice, e-way, and profit', () => {
    const { en, hi } = pageText('sales-invoice-detail');
    expect(en).toMatch(/Copy link/);
    expect(en).toMatch(/Revoke link/);
    expect(en).toMatch(/Cancelled/);
    expect(en).toMatch(/full return/i);
    expect(en).toMatch(/sandbox/i);
    expect(en).toMatch(/NIC/);
    expect(en).toMatch(/kilometres/i);
    expect(en).toMatch(/service-only/i);
    expect(en).toMatch(/GST collected/);
    expect(hi.length).toBeGreaterThan(80);
  });

  it('FAQs name preview, the public link, profit, and quick settings', () => {
    const preview = faqText('invoice-preview-amounts');
    expect(preview).toMatch(/Preview Mode/);
    expect(preview).toMatch(/amount in words/i);
    expect(preview).toMatch(/unit price/i);

    const link = faqText('public-invoice-link');
    expect(link).toMatch(/Copy link/);
    expect(link).toMatch(/purchase price/i);
    expect(link).toMatch(/Profit Details/);
    expect(link).toMatch(/Cancelled/);
    expect(link).toMatch(/payment gateway credentials/i);

    const profit = faqText('invoice-profit-details');
    expect(profit).toMatch(/Est\. Margin/);
    expect(profit).toMatch(/GST collected/);
    expect(profit).toMatch(/public link/i);

    const settings = faqText('invoice-quick-settings');
    expect(settings).toMatch(/purchase price/i);
    expect(settings).toMatch(/Party custom fields/);
    expect(settings).toMatch(/PO number/i);
  });

  it('complete and e-invoice answers match the bill rules', () => {
    const complete = HELP_INTENTS.find((row) => row.intentId === 'cannot-complete-invoice')!;
    expect(complete.answer.en).toMatch(/only cash/i);
    expect(complete.answer.en).toMatch(/tracking off/i);
    expect(complete.answer.hi).toMatch(/नकद/);

    const einvoice = HELP_INTENTS.find((row) => row.intentId === 'einvoice-irp-not-live')!;
    expect(einvoice.answer.en).toMatch(/Generate e-Invoice/);
    expect(einvoice.answer.en).toMatch(/sandbox/i);
    expect(einvoice.answer.en).toMatch(/NIC/);
    expect(einvoice.answer.hi).toMatch(/NIC/);

    const share = HELP_INTENTS.find((row) => row.intentId === 'pdf-or-share-unavailable')!;
    expect(share.answer.en).toMatch(/Copy link/);
    expect(share.answer.en).toMatch(/Preview Mode/);
  });
});
