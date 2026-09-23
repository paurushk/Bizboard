import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { DraftLineTable } from '@/components/billing/DraftLineTable';
import type { DraftLine } from '@/components/billing/types';
import { calculateLineTax } from '@/utils/tax';

const line: DraftLine = {
  key: 'l1',
  product: 4,
  productName: 'Widget',
  description: '',
  sku: 'W-1',
  hsnCode: '998811',
  unitName: 'PCS',
  batchNo: '',
  expDate: '',
  mfgDate: '',
  mrp: 0,
  quantity: 1,
  unitPrice: 1000,
  discountPercent: 0,
  discountAmount: 0,
  gstRate: 18,
  cessRate: 0,
  taxableAmount: 1000,
  cgst: 90,
  sgst: 90,
  igst: 0,
  cess: 0,
  lineTotal: 1180,
  gross: 1000,
};

describe('DraftLineTable TAX/AMOUNT from preview (#15)', () => {
  it('shows TAX and AMOUNT columns using preview-fed line tax', () => {
    const tax = calculateLineTax({
      quantity: 1,
      unitPrice: 1000,
      gstRate: 18,
      intraState: true,
    });
    render(
      <DraftLineTable
        lines={[line]}
        taxes={[tax]}
        showCess={false}
        onUpdate={() => undefined}
        onDelete={() => undefined}
      />,
    );
    expect(screen.getByText('TAX')).toBeTruthy();
    expect(screen.getByText('AMOUNT (₹)')).toBeTruthy();
    expect(screen.getByText('18%')).toBeTruthy();
  });
});
