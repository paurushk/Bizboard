import { describe, expect, it } from 'vitest';
import { mapPreviewTotals } from './sales';

describe('mapPreviewTotals — estimated margin fields', () => {
  it('maps snake_case margin fields from the backend response', () => {
    const totals = mapPreviewTotals({
      subtotal: '2000.00',
      grand_total: '2360.00',
      estimated_cogs: '160.00',
      estimated_margin: '1840.00',
      estimated_margin_percent: '92.00',
      margin_estimate_partial: false,
    });
    expect(totals.estimatedCogs).toBe(160);
    expect(totals.estimatedMargin).toBe(1840);
    expect(totals.estimatedMarginPercent).toBe(92);
    expect(totals.marginEstimatePartial).toBe(false);
  });

  it('leaves margin fields undefined (not 0) when the backend omits them', () => {
    // e.g. a purchase preview, or a sales preview for a role without
    // financial-reports permission -- must not look like "zero margin".
    const totals = mapPreviewTotals({ subtotal: '2000.00', grand_total: '2360.00' });
    expect(totals.estimatedCogs).toBeUndefined();
    expect(totals.estimatedMargin).toBeUndefined();
    expect(totals.estimatedMarginPercent).toBeUndefined();
    expect(totals.marginEstimatePartial).toBeUndefined();
  });

  it('surfaces the partial-estimate flag when some lines have no cost data', () => {
    const totals = mapPreviewTotals({
      subtotal: '500.00',
      grand_total: '590.00',
      estimated_cogs: '0.00',
      estimated_margin: '500.00',
      estimated_margin_percent: '100.00',
      margin_estimate_partial: true,
    });
    expect(totals.marginEstimatePartial).toBe(true);
  });
});
