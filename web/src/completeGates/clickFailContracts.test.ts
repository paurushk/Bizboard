import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const ROOT = resolve(__dirname, '../../..');

function src(rel: string) {
  return readFileSync(resolve(ROOT, rel), 'utf8');
}

/**
 * Click-fail Complete gates (period / confirms) stay named via
 * completeWithConfirms — they must not silently disable Complete.
 */
describe('Complete click-fail contracts', () => {
  it('CG-11 / CG-12: sales complete uses completeWithConfirms for named confirms', () => {
    const page = src('web/src/pages/sales/NewInvoicePage.tsx');
    expect(page).toContain('completeWithConfirms');
  });

  it('CG-14: completed IRN lock is a named Complete/save blocker', () => {
    const page = src('web/src/pages/sales/NewInvoicePage.tsx');
    expect(page).toContain('hasLiveIrn');
    expect(page).toContain('irnLocked');
    expect(page).toContain('einvoice.lineAmendBlocked');
  });

  it('CG-21 / CG-22 / CG-23: purchase complete uses completeWithConfirms (no-RCM, duplicate bill, period)', () => {
    const page = src('web/src/pages/purchases/NewPurchasePage.tsx');
    expect(page).toContain('completeWithConfirms');
  });

  it('CG-04 / CG-18: sales and purchase editors gate Complete on previewAllowsComplete', () => {
    expect(src('web/src/pages/sales/NewInvoicePage.tsx')).toContain('previewAllowsComplete');
    expect(src('web/src/pages/purchases/NewPurchasePage.tsx')).toContain('previewAllowsComplete');
  });

  it('CG-14: InvoiceDetailPage and NewInvoicePage share the live-IRN named lock', () => {
    const editor = src('web/src/pages/sales/NewInvoicePage.tsx');
    const detail = src('web/src/pages/sales/InvoiceDetailPage.tsx');
    expect(editor).toContain('hasLiveIrn');
    expect(detail).toContain('completeWithConfirms');
  });

  it('CG-12: sales completeWithConfirms maps duplicate / GSTIN / blank-POS confirm codes', () => {
    const helper = src('web/src/utils/completeWithConfirms.ts');
    expect(helper).toContain('confirm_duplicate_bill');
    expect(helper).toContain('GSTIN_TOTAL_CHANGED');
    expect(helper).toContain('confirm_no_rcm');
  });

  it('CG-37: payroll and work-order Complete name writes-blocked', () => {
    expect(src('web/src/pages/payroll/PayRunsPage.tsx')).toContain('billing.writesBlocked');
    expect(src('web/src/pages/manufacturing/WorkOrdersPage.tsx')).toContain('billing.writesBlocked');
  });
});
