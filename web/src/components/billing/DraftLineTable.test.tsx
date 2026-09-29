import { render, screen, within } from '@testing-library/react';
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

function makeLine(overrides: Partial<DraftLine>): DraftLine {
  return { ...line, ...overrides };
}

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

describe('DraftLineTable renderPriceHint (price-jump note slot)', () => {
  it('renders normally with no extra content near the rate field when renderPriceHint is not passed', () => {
    render(
      <DraftLineTable
        lines={[line]}
        taxes={[undefined]}
        showCess={false}
        onUpdate={() => undefined}
        onDelete={() => undefined}
      />,
    );
    const priceInput = screen.getByDisplayValue('1000');
    const priceCell = priceInput.closest('td');
    expect(priceCell).toBeTruthy();
    // Nothing but the rate input itself in this cell — no stray hint text.
    // (MUI's outlined-fieldset legend renders a zero-width-space placeholder
    // even with no label, so strip that before checking for real content.)
    expect(priceCell?.textContent?.replace(/[\u200B\s]/g, '')).toBe('');
  });

  it('calls renderPriceHint per line and renders each result under the correct rate field', () => {
    const lineA = makeLine({ key: 'a', productName: 'Widget A', unitPrice: 1000 });
    const lineB = makeLine({ key: 'b', productName: 'Widget B', unitPrice: 2000 });
    render(
      <DraftLineTable
        lines={[lineA, lineB]}
        taxes={[undefined, undefined]}
        showCess={false}
        onUpdate={() => undefined}
        onDelete={() => undefined}
        renderPriceHint={(l) => `TEST_HINT_${l.key}`}
      />,
    );

    const priceInputA = screen.getByDisplayValue('1000');
    const priceInputB = screen.getByDisplayValue('2000');
    const cellA = priceInputA.closest('td') as HTMLElement;
    const cellB = priceInputB.closest('td') as HTMLElement;

    expect(within(cellA).getByText('TEST_HINT_a')).toBeTruthy();
    expect(within(cellA).queryByText('TEST_HINT_b')).toBeNull();
    expect(within(cellB).getByText('TEST_HINT_b')).toBeTruthy();
    expect(within(cellB).queryByText('TEST_HINT_a')).toBeNull();
  });

  it('renders nothing extra for a line where renderPriceHint returns null, without an empty wrapper', () => {
    const lineA = makeLine({ key: 'a', productName: 'Widget A', unitPrice: 1000 });
    const lineB = makeLine({ key: 'b', productName: 'Widget B', unitPrice: 2000 });
    render(
      <DraftLineTable
        lines={[lineA, lineB]}
        taxes={[undefined, undefined]}
        showCess={false}
        onUpdate={() => undefined}
        onDelete={() => undefined}
        renderPriceHint={(l) => (l.key === 'a' ? 'TEST_HINT_a' : null)}
      />,
    );

    const priceInputA = screen.getByDisplayValue('1000');
    const priceInputB = screen.getByDisplayValue('2000');
    const cellA = priceInputA.closest('td') as HTMLElement;
    const cellB = priceInputB.closest('td') as HTMLElement;

    expect(within(cellA).getByText('TEST_HINT_a')).toBeTruthy();
    // Line B's hint is null — no leftover empty <Typography> wrapper, no text.
    expect(cellB.querySelector('.MuiTypography-root')).toBeNull();
    expect(cellB.textContent?.replace(/[\u200B\s]/g, '')).toBe('');
  });
});
