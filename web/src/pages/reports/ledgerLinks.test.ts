import { describe, expect, it } from 'vitest';
import { cashBookRowPath, rateScanRowPath, registerRowPath, trialBalanceRowPath } from '@/pages/reports/ledgerLinks';

describe('registerRowPath', () => {
  it('opens an invoice, a credit note or a debit note on the right page', () => {
    expect(registerRowPath('sales', { id: 7 })).toBe('/sales/history/7');
    expect(registerRowPath('sales', { id: 8, doc_type: 'SALES_CREDIT_NOTE' })).toBe('/sales/credit-notes/8');
    expect(registerRowPath('sales', { id: 9, doc_type: 'SALES_DEBIT_NOTE' })).toBe('/sales/debit-notes/9');
    expect(registerRowPath('purchases', { id: 3 })).toBe('/purchases/history/3');
    expect(registerRowPath('purchases', { id: 4, docType: 'PURCHASE_CREDIT_NOTE' })).toBe('/purchases/credit-notes/4');
    expect(registerRowPath('purchases', { id: 5, doc_type: 'PURCHASE_DEBIT_NOTE' })).toBe('/purchases/debit-notes/5');
  });
  it('gives no link without an id', () => {
    expect(registerRowPath('sales', {})).toBeNull();
  });
});

describe('trialBalanceRowPath', () => {
  it('opens the Day Book for the account over the range', () => {
    expect(trialBalanceRowPath(12, '2026-04-01', '2026-10-18')).toBe('/reports/day-book?account=12&from=2026-04-01&to=2026-10-18');
  });
  it('gives no link without an account id', () => {
    expect(trialBalanceRowPath(undefined, 'a', 'b')).toBeNull();
  });
});

describe('cashBookRowPath', () => {
  it('finds a receipt by its number and a payment by its supplier', () => {
    expect(cashBookRowPath({ type: 'RECEIPT', number: 'RCT-0007' })).toBe('/sales/receipts?q=RCT-0007');
    expect(cashBookRowPath({ type: 'SUPPLIER_PAYMENT', party_id: 4 })).toBe('/purchases/payments?supplier=4');
    expect(cashBookRowPath({ type: 'SUPPLIER_PAYMENT' })).toBe('/purchases/payments');
  });
  it('gives no link for other rows', () => {
    expect(cashBookRowPath({ type: 'SOMETHING' })).toBeNull();
    expect(cashBookRowPath({ type: 'RECEIPT' })).toBeNull();
  });
});

describe('rateScanRowPath', () => {
  it('opens the invoice', () => {
    expect(rateScanRowPath({ invoiceId: 12 })).toBe('/sales/history/12');
    expect(rateScanRowPath({ invoice_id: 13 })).toBe('/sales/history/13');
    expect(rateScanRowPath({})).toBeNull();
  });
});
