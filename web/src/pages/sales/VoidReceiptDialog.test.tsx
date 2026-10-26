import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import type { CustomerReceipt } from '@/types/domain';
import { VoidReceiptDialog } from '@/pages/sales/VoidReceiptDialog';

const receipt = {
  id: 7,
  receiptNumber: 'RCT-0007',
  customerName: 'Sharma Traders',
  amount: '50.00',
  allocated: '0.00',
  receiptDate: '2026-10-23',
} as unknown as CustomerReceipt;

function renderDialog(narrow: boolean) {
  render(
    <MemoryRouter>
      <VoidReceiptDialog
        target={receipt}
        narrow={narrow}
        pending={false}
        error={null}
        errorSource={null}
        onCancel={vi.fn()}
        onConfirm={vi.fn()}
      />
    </MemoryRouter>,
  );
}

describe('VoidReceiptDialog', () => {
  // The phone e2e run found the bottom sheet was not exposed as a dialog at all.
  it.each([
    ['phone bottom sheet', true],
    ['desktop dialog', false],
  ])('the %s is a labelled modal dialog holding the reason field', (_label, narrow) => {
    renderDialog(narrow);
    const dialog = screen.getByRole('dialog', { name: 'Void' });
    expect(dialog).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: /Reason for voiding/ })).toBeInTheDocument();
    expect(dialog).toContainElement(screen.getByRole('textbox', { name: /Reason for voiding/ }));
  });
});
