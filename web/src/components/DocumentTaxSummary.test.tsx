import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { DocumentTaxSummary } from '@/components/DocumentTaxSummary';

describe('DocumentTaxSummary preview totals (#15)', () => {
  it('renders taxable, GST, and total amount from the preview payload', () => {
    render(
      <DocumentTaxSummary
        totals={{
          taxableTotal: 1000,
          cgstTotal: 90,
          sgstTotal: 90,
          igstTotal: 0,
          roundOff: 0,
          grandTotal: 1180,
        }}
        additionalCharges={0}
        onAdditionalChargesChange={() => undefined}
        invoiceDiscount={0}
        onInvoiceDiscountChange={() => undefined}
        invoiceDiscountMode="AFTER_TAX"
        onInvoiceDiscountModeChange={() => undefined}
        autoRoundOff
        onAutoRoundOffChange={() => undefined}
        posKnown
      />,
    );
    expect(screen.getByText('Taxable Amount')).toBeTruthy();
    expect(screen.getByText('CGST')).toBeTruthy();
    expect(screen.getByText('SGST')).toBeTruthy();
    expect(screen.getByText('Total Amount')).toBeTruthy();
  });
});
