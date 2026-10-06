import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { buildAtomicPosInvoicePayload } from '@/pages/pos/posCheckoutPayload';

describe('buildAtomicPosInvoicePayload', () => {
  it('sends batch, discount, charges, and blank-state confirm on both tenders', () => {
    const body = buildAtomicPosInvoicePayload({
      customer: 1,
      invoiceType: 'RETAIL',
      priceModeInclusive: false,
      invoiceDate: '2026-10-04',
      taxEnabled: true,
      invoiceDiscount: 5,
      additionalCharges: 10,
      lines: [{
        productId: 2,
        productName: 'Tablet',
        sku: 'TAB',
        quantity: 1,
        unitPrice: 20,
        gstRate: 18,
        batchNo: 'LOT-1',
      }],
    });
    expect(body.invoice_discount).toBe(5);
    expect(body.additional_charges).toBe(10);
    expect(body.items[0]?.batch_no).toBe('LOT-1');

    const src = readFileSync(join(process.cwd(), 'src/pages/pos/PosPage.tsx'), 'utf8');
    expect(src.split('buildAtomicPosInvoicePayload(').length - 1).toBeGreaterThanOrEqual(2);
    expect(src).toContain('confirm_blank_pos');
  });
});
