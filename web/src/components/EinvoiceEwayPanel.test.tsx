import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import type { ReactElement } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { EinvoiceEwayPanel } from '@/components/EinvoiceEwayPanel';
import type { SalesInvoice } from '@/types/domain';

vi.mock('@/api/resources', () => ({
  cancelInvoiceEinvoice: vi.fn(),
  cancelInvoiceEway: vi.fn(),
  markInvoiceEinvoiceGenerated: vi.fn(),
  markInvoiceEwayGenerated: vi.fn(),
  prepareInvoiceEinvoice: vi.fn(),
  prepareInvoiceEway: vi.fn(),
  submitInvoiceEinvoice: vi.fn(),
  submitInvoiceEway: vi.fn(),
}));

function wrap(ui: ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

const baseInvoice: SalesInvoice = {
  id: 1,
  status: 'COMPLETED',
  invoiceType: 'GST',
  invoiceDate: '2026-03-15',
  customer: 1,
  items: [],
  balance: '100',
  subtotal: '100',
  discountTotal: '0',
  taxableTotal: '100',
  cgstTotal: '0',
  sgstTotal: '0',
  igstTotal: '0',
  roundOff: '0',
  grandTotal: '100',
};

describe('EinvoiceEwayPanel — CFT-116 IRN lock', () => {
  it('shows the line-amend lock on the same screen as a live IRN', () => {
    wrap(
      <EinvoiceEwayPanel
        invoice={{ ...baseInvoice, einvoiceStatus: 'GENERATED', irn: 'IRN-LIVE' }}
      />,
    );
    expect(screen.getByText(/Line edits are blocked while this IRN is live/i)).toBeTruthy();
    expect(screen.getByText(/Saved IRN: IRN-LIVE/)).toBeTruthy();
  });
});
