import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { getContextHelpPage, resolveContextHelpPage } from '@/contextHelp';
import { FAQ_ITEMS } from './faqContent';

function faqText(id: string): string {
  const item = FAQ_ITEMS.find((row) => row.id === id);
  expect(item, id).toBeTruthy();
  return render(<>{item!.answer}</>).container.textContent ?? '';
}

const CUSTOMER_FAQS = [
  'blocked-customer',
  'customer-credit-limit',
  'duplicate-customer-gstin',
  'walk-in-customer',
  'customer-verify-gstin',
  'customer-gstin-unverified',
  'customer-edit-gstin-resets',
  'customer-state-mismatch',
  'customer-who-can',
  'customer-block-archive-delete',
  'customer-archive-refused',
  'customer-archived-billing',
  'customer-360',
  'customer-history',
  'customer-export',
  'customer-changed-by-someone',
  'customer-phone-format',
  'customer-pos-walk-in',
  'customer-addresses-fields',
  'customer-tax-class',
  'customer-health-banner',
  'customer-summary-cards',
];

describe('customers help pages', () => {
  it('shows the customers page on the list and the snapshot page on a customer', () => {
    expect(resolveContextHelpPage('/sales/customers')).toBe('customers');
    expect(resolveContextHelpPage('/sales/customers/12')).toBe('customer-360');
  });

  it('has a Hindi line for every section of both pages', () => {
    for (const id of ['customers', 'customer-360']) {
      const page = getContextHelpPage(id);
      expect(page, id).toBeTruthy();
      const parts = [
        page!.title,
        page!.summary,
        ...page!.howItWorks,
        ...page!.businessImpact,
        ...page!.keyRules,
        ...page!.commonMistakes,
        ...page!.nextActions,
      ];
      for (const part of parts) expect(part.hi?.trim(), `${id}: ${part.en}`).toBeTruthy();
    }
  });

  it('explains who may do what, and what blocked and archived customers cannot get', () => {
    const page = getContextHelpPage('customers')!;
    const en = [...page.howItWorks, ...page.businessImpact, ...page.keyRules].map((part) => part.en).join('\n');
    expect(en).toMatch(/Anyone who can create sales may Block/);
    expect(en).toMatch(/Unblock, Activate, Archive, and credit terms are for an owner or manager/);
    expect(en).toMatch(/blocked or archived customer cannot get a new invoice/);
    expect(en).toMatch(/Archive is refused while the customer owes money/);
    expect(en).toMatch(/Verify selected to check up to 10/);
    expect(en).toMatch(/20,000 rows/);
  });

  it('describes the snapshot page: edit in place, history, promises, permissions', () => {
    const page = getContextHelpPage('customer-360')!;
    const en = [...page.howItWorks, ...page.keyRules].map((part) => part.en).join('\n');
    expect(en).toMatch(/Edit customer opens the same form/);
    expect(en).toMatch(/History lists who changed the customer/);
    expect(en).toMatch(/Log a promise to pay/);
    expect(en).toMatch(/financial-reports permission/);
  });
});

describe('customer FAQs', () => {
  it('are all present, in the Customers category, with search keywords', () => {
    for (const id of CUSTOMER_FAQS) {
      const item = FAQ_ITEMS.find((row) => row.id === id);
      expect(item, id).toBeTruthy();
      expect(item!.category, id).toBe('Customers');
      expect((item!.keywords ?? []).length, id).toBeGreaterThan(2);
    }
  });

  it('give the current rules for roles, archive and blocked customers', () => {
    expect(faqText('customer-who-can')).toMatch(/Unblock.*Activate.*Archive.*owner or manager/);
    expect(faqText('blocked-customer')).toMatch(/blocked or archived/);
    expect(faqText('customer-archive-refused')).toMatch(/owes money, or holds an advance/);
    expect(faqText('customer-archived-billing')).toMatch(/cannot get a new invoice/);
    expect(faqText('duplicate-customer-gstin')).toMatch(/names the customer/);
  });

  it('explain GSTIN checks, phone numbers and conflicts in plain words', () => {
    expect(faqText('customer-verify-gstin')).toMatch(/up to 10 at once/);
    expect(faqText('customer-gstin-unverified')).toMatch(/only the format and check digit/);
    expect(faqText('customer-state-mismatch')).toMatch(/first two digits of a GSTIN are its state/);
    expect(faqText('customer-phone-format')).toMatch(/9123456789, is valid/);
    expect(faqText('customer-changed-by-someone')).toMatch(/Reload latest/);
  });
});
