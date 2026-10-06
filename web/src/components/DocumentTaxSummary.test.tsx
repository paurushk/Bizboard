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

  it('gives every amount input and the discount mode picker an accessible name (UX-N03/N04)', () => {
    render(
      <DocumentTaxSummary
        totals={{ taxableTotal: 1000, cgstTotal: 90, sgstTotal: 90, igstTotal: 0, roundOff: 0, grandTotal: 1180 }}
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
    expect(screen.getByRole('textbox', { name: 'Collect as' })).toBeTruthy();
    expect(screen.getByRole('textbox', { name: 'Additional Charges' })).toBeTruthy();
    expect(screen.getAllByRole('textbox', { name: 'Invoice discount' }).length).toBe(1);
    expect(screen.getByRole('combobox', { name: 'Invoice discount' })).toBeTruthy();
  });
});
