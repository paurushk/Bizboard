import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import type { BillTotals } from '@/types/domain';
import { BillTotalsPanel } from './BillTotalsPanel';

const totals = (over: Partial<BillTotals> = {}): BillTotals => ({
  taxable: '400.00',
  gst: '72.00',
  cess: '0.00',
  charges: '0.00',
  invoiceDiscount: '0.00',
  grandTotal: '472.00',
  roundedTotal: '472',
  includedLines: 2,
  ...over,
});

function show(over: Partial<React.ComponentProps<typeof BillTotalsPanel>> = {}) {
  const handlers = {
    onPriceMode: vi.fn(),
    onAdditionalCharges: vi.fn(),
    onInvoiceDiscount: vi.fn(),
    onPrintedTotal: vi.fn(),
  };
  render(
    <BillTotalsPanel
      totals={totals()}
      priceMode="EXCLUSIVE"
      additionalCharges=""
      invoiceDiscount=""
      printedTotal=""
      {...handlers}
      {...over}
    />,
  );
  return handlers;
}

describe('BillTotalsPanel', () => {
  it('shows the totals the draft will have', () => {
    show();
    expect(screen.getByText('400.00')).toBeInTheDocument();
    expect(screen.getByText('472.00')).toBeInTheDocument();
    expect(screen.getByText('Totals as the draft will have them')).toBeInTheDocument();
  });

  it('shows dashes until the server has produced totals', () => {
    show({ totals: undefined });
    expect(screen.getAllByText('—').length).toBeGreaterThanOrEqual(3);
  });

  it('hides cess, charges and discount when they are zero and shows them when they are not', () => {
    const { rerender } = render(
      <BillTotalsPanel
        totals={totals()}
        priceMode="EXCLUSIVE"
        additionalCharges=""
        invoiceDiscount=""
        printedTotal=""
        onPriceMode={vi.fn()}
        onAdditionalCharges={vi.fn()}
        onInvoiceDiscount={vi.fn()}
        onPrintedTotal={vi.fn()}
      />,
    );
    expect(screen.queryByText('Cess')).not.toBeInTheDocument();
    expect(screen.queryByText('Charges')).not.toBeInTheDocument();
    expect(screen.queryByText('Discount')).not.toBeInTheDocument();
    rerender(
      <BillTotalsPanel
        totals={totals({ cess: '30.00', charges: '50.00', invoiceDiscount: '20.00' })}
        priceMode="EXCLUSIVE"
        additionalCharges=""
        invoiceDiscount=""
        printedTotal=""
        onPriceMode={vi.fn()}
        onAdditionalCharges={vi.fn()}
        onInvoiceDiscount={vi.fn()}
        onPrintedTotal={vi.fn()}
      />,
    );
    expect(screen.getByText('Cess')).toBeInTheDocument();
    expect(screen.getByText('Charges')).toBeInTheDocument();
    expect(screen.getByText('Discount')).toBeInTheDocument();
  });

  it('splits GST into CGST and SGST for a same-state bill', () => {
    show({ totals: totals({ cgst: '36.00', sgst: '36.00', igst: '0.00', taxType: 'INTRA' }) });
    expect(screen.getByText('CGST')).toBeInTheDocument();
    expect(screen.getByText('SGST')).toBeInTheDocument();
    expect(screen.queryByText('IGST')).not.toBeInTheDocument();
    expect(screen.queryByText(/split is assumed/i)).not.toBeInTheDocument();
  });

  it('shows IGST for an inter-state bill', () => {
    show({ totals: totals({ cgst: '0.00', sgst: '0.00', igst: '72.00', taxType: 'INTER' }) });
    expect(screen.getByText('IGST')).toBeInTheDocument();
    expect(screen.queryByText('CGST')).not.toBeInTheDocument();
  });

  it('says the split is assumed until the customer is known', () => {
    show({ totals: totals({ cgst: '36.00', sgst: '36.00', igst: '0.00', taxType: 'ASSUMED_INTRA' }) });
    expect(screen.getByText(/split is assumed/i)).toBeInTheDocument();
  });

  it('falls back to a single GST figure when the split is not available', () => {
    show();
    expect(screen.getByText('GST')).toBeInTheDocument();
    expect(screen.getByText('72.00')).toBeInTheDocument();
  });

  it('shows why the totals could not be worked out', () => {
    show({ totals: totals({ error: 'Invoice discount 999.00 exceeds the invoice value 59.00.' }) });
    expect(screen.getByText(/exceeds the invoice value/)).toBeInTheDocument();
  });

  it('marks a matching printed total and reports a difference otherwise', () => {
    const { unmount } = render(
      <BillTotalsPanel
        totals={totals({ printedTotal: '472.00', printedDifference: '0.00', printedMatches: true })}
        priceMode="EXCLUSIVE"
        additionalCharges=""
        invoiceDiscount=""
        printedTotal="472"
        onPriceMode={vi.fn()}
        onAdditionalCharges={vi.fn()}
        onInvoiceDiscount={vi.fn()}
        onPrintedTotal={vi.fn()}
      />,
    );
    expect(screen.getByText('Matches the printed total')).toBeInTheDocument();
    unmount();
    show({ totals: totals({ printedTotal: '500.00', printedDifference: '28.00', printedMatches: false }) });
    expect(screen.getByText('Difference from printed total: 28.00')).toBeInTheDocument();
  });

  it('passes every edit up', async () => {
    const user = userEvent.setup();
    const h = show();
    await user.type(screen.getByLabelText('Freight / other charges'), '5');
    expect(h.onAdditionalCharges).toHaveBeenLastCalledWith('5');
    await user.type(screen.getByLabelText('Bill discount'), '2');
    expect(h.onInvoiceDiscount).toHaveBeenLastCalledWith('2');
    await user.type(screen.getByLabelText('Total printed on the bill'), '9');
    expect(h.onPrintedTotal).toHaveBeenLastCalledWith('9');
  });

  it('switches between prices without and with GST', async () => {
    const user = userEvent.setup();
    const h = show();
    await user.click(screen.getByRole('combobox', { name: 'Prices on this bill' }));
    await user.click(await screen.findByRole('option', { name: 'With GST included' }));
    expect(h.onPriceMode).toHaveBeenCalledWith('INCLUSIVE');
  });
});
