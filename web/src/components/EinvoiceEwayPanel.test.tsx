import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactElement } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { EinvoiceEwayPanel } from '@/components/EinvoiceEwayPanel';
import { t } from '@/i18n';
import type { SalesInvoice } from '@/types/domain';

vi.mock('@/api/resources', () => ({
  cancelInvoiceEinvoice: vi.fn(),
  cancelInvoiceEway: vi.fn(),
  markInvoiceEinvoiceGenerated: vi.fn(),
  markInvoiceEwayGenerated: vi.fn(),
  prepareInvoiceEinvoice: vi.fn(),
  prepareInvoiceEway: vi.fn(),
  postPlanEwayStub: vi.fn(),
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

  it('names a sandbox acknowledgement and does not claim a portal filing', () => {
    const text = t('einvoice.submittedSandbox');
    expect(text).toMatch(/Sandbox acknowledgement only/i);
    expect(text).not.toMatch(/filed|GSTN|IRP portal/i);
  });

  it('shows the sandbox acknowledgement on the panel before submit', () => {
    wrap(<EinvoiceEwayPanel invoice={baseInvoice} />);
    expect(screen.getByText(t('einvoice.submittedSandbox'))).toBeTruthy();
    expect(screen.getByText(t('einvoice.submittedSandbox')).textContent ?? '').not.toMatch(
      /filed|GSTN|IRP portal/i,
    );
  });
});

describe('EinvoiceEwayPanel — saved values follow the invoice', () => {
  const irnBox = () => screen.getByLabelText('IRN') as HTMLInputElement;
  const panel = (invoice: SalesInvoice) => (
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <EinvoiceEwayPanel invoice={invoice} />
    </QueryClientProvider>
  );

  it('starts with the invoice IRN and acknowledgement number', () => {
    render(panel({ ...baseInvoice, einvoiceStatus: 'GENERATED', irn: 'IRN-1', ackNo: 'ACK-1' }));
    expect(irnBox().value).toBe('IRN-1');
    expect((screen.getByLabelText('Ack No') as HTMLInputElement).value).toBe('ACK-1');
  });

  it('shows the new IRN when the invoice is refreshed with one', () => {
    const { rerender } = render(panel({ ...baseInvoice, irn: 'IRN-1' }));
    rerender(panel({ ...baseInvoice, irn: 'IRN-2' }));
    expect(irnBox().value).toBe('IRN-2');
  });

  it('keeps what the user typed when the invoice refreshes with the same IRN', () => {
    const { rerender } = render(panel({ ...baseInvoice, irn: 'IRN-1' }));
    fireEvent.change(irnBox(), { target: { value: 'IRN-TYPED' } });
    rerender(panel({ ...baseInvoice, irn: 'IRN-1', notes: 'edited elsewhere' } as SalesInvoice));
    expect(irnBox().value).toBe('IRN-TYPED');
  });

  it('stores a Part B vehicle update on the stub, with live filing left off', async () => {
    const user = userEvent.setup();
    const resources = await import('@/api/resources');
    vi.mocked(resources.postPlanEwayStub).mockResolvedValue({ id: 9 });
    wrap(<EinvoiceEwayPanel invoice={{ ...baseInvoice, vehicleNumber: 'KA01AB1234' }} />);
    const button = screen.getByRole('button', { name: t('sweep2.partBUpdate') });
    expect(button).toBeEnabled();
    await user.click(button);
    await waitFor(() => {
      expect(resources.postPlanEwayStub).toHaveBeenCalledWith(
        expect.objectContaining({ action: 'PART_B', documentId: 1, billStatus: 'ACTIVE' }),
      );
    });
  });

  it('empties the boxes when the invoice has no IRN', () => {
    const { rerender } = render(panel({ ...baseInvoice, irn: 'IRN-1' }));
    rerender(panel({ ...baseInvoice, irn: undefined }));
    expect(irnBox().value).toBe('');
  });
});
