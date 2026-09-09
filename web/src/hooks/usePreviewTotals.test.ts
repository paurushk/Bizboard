import { describe, expect, it } from 'vitest';
import { mapPreviewTotals } from '@/api/legacy/sales';

describe('mapPreviewTotals (A-03)', () => {
  it('binds displayed GST and grand total from the preview response', () => {
    const totals = mapPreviewTotals({
      subtotal: '100.00',
      cgst_total: '9.00',
      sgst_total: '9.00',
      igst_total: '0',
      cess_total: '1.00',
      grand_total: '119.00',
      round_off: '0',
    });
    expect(totals.cgstTotal).toBe(9);
    expect(totals.sgstTotal).toBe(9);
    expect(totals.cessTotal).toBe(1);
    expect(totals.taxTotal).toBe(19);
    expect(totals.grandTotal).toBe(119);
  });

  it('reads camelCase envelope keys', () => {
    const totals = mapPreviewTotals({ cgstTotal: 45, sgstTotal: 45, grandTotal: 590 });
    expect(totals.grandTotal).toBe(590);
    expect(totals.taxTotal).toBe(90);
  });

  it('maps rcm_cess / rcmCgst from the preview JSON', () => {
    const totals = mapPreviewTotals({
      cgst_total: '0',
      sgst_total: '0',
      grand_total: '1000.00',
      rcm_taxable: '1000.00',
      rcm_cgst: '90.00',
      rcm_sgst: '90.00',
      rcmCess: '10.00',
    });
    expect(totals.rcmCgst).toBe(90);
    expect(totals.rcmSgst).toBe(90);
    expect(totals.rcmCess).toBe(10);
    expect(totals.taxTotal).toBe(0);
  });
});
