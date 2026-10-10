import { describe, expect, it } from 'vitest';
import { buildQuotationPayload, buildQuotationPreviewBody, type QuotationFormState } from './quotationPayload';

const form: QuotationFormState = {
  customerId: 7,
  quotationDate: '2026-10-05',
  validUntil: '2026-10-30',
  salesman: '3',
  salesChannel: 'ONLINE',
  deliveryAddress: 'Dock 4',
  invoiceType: 'GST',
  lines: [{ id: 11, productId: 2, qty: 2.5, unitPrice: 100, discountPercent: 5, expectedPrice: 60, gstRate: 18 }],
};

describe('buildQuotationPayload', () => {
  it('create sends the selected date and the invoice type', () => {
    const p = buildQuotationPayload(form, 'create');
    expect(p.quotationDate).toBe('2026-10-05');
    expect(p.invoiceType).toBe('GST');
    expect(p.customer).toBe(7);
  });

  it('edit keeps the stored invoice type', () => {
    const p = buildQuotationPayload(form, 'edit');
    expect('invoiceType' in p).toBe(false);
    expect(p.customer).toBe(7);
  });

  it('partially converted edit sends only the whitelisted header fields', () => {
    const p = buildQuotationPayload(form, 'edit-partially-converted');
    expect(Object.keys(p).sort()).toEqual(['deliveryAddress', 'salesChannel', 'salesman', 'validUntil']);
  });

  it('passes decimal quantities and line ids through unchanged', () => {
    const items = buildQuotationPayload(form, 'edit').items as Array<Record<string, unknown>>;
    expect(items[0]).toMatchObject({ id: 11, quantity: 2.5, product: 2 });
  });

  it('omits internal cost when the user cannot see it', () => {
    const items = buildQuotationPayload(form, 'edit', { includeCost: false }).items as Array<Record<string, unknown>>;
    expect('expectedPrice' in items[0]).toBe(false);
  });

  it('sends null for an empty valid-until and salesman', () => {
    const p = buildQuotationPayload({ ...form, validUntil: '', salesman: '' }, 'create');
    expect(p.validUntil).toBeNull();
    expect(p.salesman).toBeNull();
  });
});

describe('commercial fields and line extras', () => {
  const full: QuotationFormState = {
    ...form,
    notes: 'n',
    termsText: 't',
    paymentTermsDays: 15,
    additionalCharges: 100,
    chargesHsn: '9965',
    chargesGstRate: 18,
    invoiceDiscount: 50,
    invoiceDiscountMode: 'BEFORE_TAX',
    autoRoundOff: false,
    lines: [{ ...form.lines[0], hsnCode: '3004', cessRate: 12, unitPriceInclusive: 118 }],
  };

  it('create and edit send the commercial terms and the carried line fields', () => {
    for (const mode of ['create', 'edit'] as const) {
      const p = buildQuotationPayload(full, mode);
      expect(p).toMatchObject({
        notes: 'n', termsText: 't', paymentTermsDays: 15, additionalCharges: 100, chargesHsn: '9965',
        chargesGstRate: 18, invoiceDiscount: 50, invoiceDiscountMode: 'BEFORE_TAX', autoRoundOff: false,
      });
      expect((p.items as Array<Record<string, unknown>>)[0]).toMatchObject({
        hsnCode: '3004', cessRate: 12, unitPriceInclusive: 118,
      });
    }
  });

  it('a partly converted quote may still change notes and terms but no money field', () => {
    const p = buildQuotationPayload(full, 'edit-partially-converted');
    expect(Object.keys(p).sort()).toEqual(
      ['deliveryAddress', 'notes', 'salesChannel', 'salesman', 'termsText', 'validUntil'],
    );
  });

  it('the preview body carries the stored header, so it matches what is saved', () => {
    const body = buildQuotationPreviewBody(full, { supplyType: 'B2B', companyGstin: 4 });
    expect(body).toMatchObject({
      customer: 7, invoiceType: 'GST', supplyType: 'B2B', companyGstin: 4, additionalCharges: 100,
      invoiceDiscount: 50, invoiceDiscountMode: 'BEFORE_TAX', autoRoundOff: false, chargesGstRate: 18,
    });
    expect((body.items as Array<Record<string, unknown>>)[0]).toMatchObject({ cessRate: 12, hsnCode: '3004' });
  });

  it('omits empty extras', () => {
    const items = buildQuotationPayload(form, 'edit').items as Array<Record<string, unknown>>;
    expect('hsnCode' in items[0]).toBe(false);
    expect('cessRate' in items[0]).toBe(false);
  });
});
