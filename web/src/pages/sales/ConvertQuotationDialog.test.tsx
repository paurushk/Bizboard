import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { ConvertQuotationDialog } from '@/pages/sales/ConvertQuotationDialog';
import type { Quotation } from '@/types/domain';

const quotation = {
  id: 9,
  status: 'DRAFT',
  invoiceType: 'GST',
  quotationDate: '2026-03-15',
  items: [
    {
      id: 1,
      product: 4,
      productName: 'Widget',
      quantity: '10',
      convertedQuantity: '4',
      unitPrice: '100',
    },
  ],
  grandTotal: '1180',
} as Quotation;

describe('ConvertQuotationDialog — CFT-115', () => {
  it('defaults convert qty to remaining and submits that payload', async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    render(
      <ConvertQuotationDialog
        quotation={quotation}
        mode="order"
        onClose={() => undefined}
        onConfirm={onConfirm}
      />,
    );
    expect(screen.getByLabelText('Convert qty')).toHaveValue(6);
    await user.click(screen.getByRole('button', { name: 'To Order' }));
    expect(onConfirm).toHaveBeenCalledWith([{ id: 1, quantity: 6 }]);
  });

  it('lets the operator convert less than remaining', async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    render(
      <ConvertQuotationDialog
        quotation={quotation}
        mode="invoice"
        onClose={() => undefined}
        onConfirm={onConfirm}
      />,
    );
    const input = screen.getByLabelText('Convert qty');
    await user.clear(input);
    await user.type(input, '2');
    await user.click(screen.getByRole('button', { name: 'Convert to invoice' }));
    expect(onConfirm).toHaveBeenCalledWith([{ id: 1, quantity: 2 }]);
  });

  it('requires confirmation checkbox when quotation validity has expired', async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    const expiredQuotation = {
      ...quotation,
      validUntil: '2020-01-01',
    };
    render(
      <ConvertQuotationDialog
        quotation={expiredQuotation}
        mode="order"
        onClose={() => undefined}
        onConfirm={onConfirm}
      />,
    );
    const submitBtn = screen.getByRole('button', { name: 'To Order' });
    expect(submitBtn).toBeDisabled();

    const checkbox = screen.getByRole('checkbox');
    expect(checkbox).not.toBeChecked();

    await user.click(checkbox);
    expect(checkbox).toBeChecked();
    expect(submitBtn).not.toBeDisabled();

    await user.click(submitBtn);
    expect(onConfirm).toHaveBeenCalledWith([{ id: 1, quantity: 6 }], true);
  });
});
