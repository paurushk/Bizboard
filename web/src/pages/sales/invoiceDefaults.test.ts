import { describe, expect, it } from 'vitest';
import { chooseInvoiceDefaults, inferInvoiceTypeFromParty } from './invoiceDefaults';

describe('chooseInvoiceDefaults', () => {
  it('uses the company type when fewer than three bills exist', () => {
    expect(
      chooseInvoiceDefaults({
        invoices: [{ invoiceType: 'NON_GST', priceMode: 'INCLUSIVE', customerName: 'Walk-in' }],
        registrationType: 'REGULAR',
        companyPriceMode: 'EXCLUSIVE',
      }),
    ).toEqual({ invoiceType: 'GST', priceMode: 'EXCLUSIVE', paymentTermsDays: 30 });
  });

  it('defaults a retail counter to walk-in terms when three of five are walk-in', () => {
    const walk = { invoiceType: 'GST', priceMode: 'INCLUSIVE', customerName: 'Walk-in Cash' };
    const account = { invoiceType: 'GST', priceMode: 'EXCLUSIVE', customerName: 'Sharma Traders' };
    expect(
      chooseInvoiceDefaults({
        invoices: [walk, walk, walk, account, account],
        registrationType: 'REGULAR',
      }),
    ).toEqual({ invoiceType: 'GST', priceMode: 'INCLUSIVE', paymentTermsDays: 0 });
  });

  it('keeps account-sale terms when walk-in bills are the minority', () => {
    const account = { invoiceType: 'NON_GST', priceMode: 'INCLUSIVE', customerName: 'Sharma' };
    expect(
      chooseInvoiceDefaults({
        invoices: [account, account, account, account, account],
        registrationType: 'COMPOSITION',
      }).paymentTermsDays,
    ).toBe(30);
  });

  it('keeps the company price mode for account sales instead of forcing exclusive', () => {
    const account = { invoiceType: 'GST', priceMode: 'EXCLUSIVE', customerName: 'Sharma' };
    expect(
      chooseInvoiceDefaults({
        invoices: [account, account, account],
        registrationType: 'REGULAR',
        companyPriceMode: 'INCLUSIVE',
      }).priceMode,
    ).toBe('INCLUSIVE');
  });
});

describe('inferInvoiceTypeFromParty', () => {
  it('posts GST for a regular company when the customer has a GSTIN', () => {
    expect(inferInvoiceTypeFromParty({
      registrationType: 'REGULAR',
      customerGstin: '29ABCDE1234F1Z5',
    })).toBe('GST');
  });

  it('posts RETAIL for a regular company when the customer has no GSTIN', () => {
    expect(inferInvoiceTypeFromParty({ registrationType: 'REGULAR', customerGstin: '' })).toBe('RETAIL');
  });

  it('keeps the company rule for a composition company', () => {
    expect(inferInvoiceTypeFromParty({ registrationType: 'COMPOSITION', customerGstin: '29ABCDE1234F1Z5' })).toBe('NON_GST');
  });
});
