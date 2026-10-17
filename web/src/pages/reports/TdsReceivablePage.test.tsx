import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { TdsReceivablePage } from '@/pages/reports/TdsReceivablePage';

const { getTdsReceivableReport, exportTdsReceivableCsv, triggerBlobDownload, auth, setReceiptTdsCertificate } = vi.hoisted(() => ({
  getTdsReceivableReport: vi.fn(),
  setReceiptTdsCertificate: vi.fn(async () => ({})),
  exportTdsReceivableCsv: vi.fn(async () => new Blob(['a'], { type: 'text/csv' })),
  triggerBlobDownload: vi.fn(),
  auth: { role: 'OWNER', canExport: true, canCreatePayments: true },
}));

vi.mock('@/api/resources', () => ({
  getTdsReceivableReport: (...args: unknown[]) => getTdsReceivableReport(...args),
  exportTdsReceivableCsv: (...args: unknown[]) => exportTdsReceivableCsv(...args),
  setReceiptTdsCertificate: (...args: unknown[]) => setReceiptTdsCertificate(...args),
}));
vi.mock('@/utils/blob', () => ({ triggerBlobDownload: (...args: unknown[]) => triggerBlobDownload(...args) }));
vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ user: { id: 1, email: 'o@x.test', fullName: 'O', role: auth.role, canExport: auth.canExport, canCreatePayments: auth.canCreatePayments, companyId: 9 } }),
}));

const ROW = {
  receiptId: 1, receiptNumber: 'RCT-0001', receiptDate: '2026-10-01', customerId: 3, customer: 'Ravi Traders',
  pan: 'ABCDE1234F', section: '194C', amountReceived: '900.00', tdsDeducted: '100.00', tdsApplied: '100.00', tdsUnapplied: '0.00',
};

function wrap(path = '/') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <TdsReceivablePage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('TdsReceivablePage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    auth.role = 'OWNER';
    auth.canExport = true;
    auth.canCreatePayments = true;
  });

  it('lists receipts with PAN and section, and the total deducted', async () => {
    getTdsReceivableReport.mockResolvedValue({ rows: [ROW], totalTds: '100.00', count: 1 });
    wrap();
    expect(await screen.findByText('RCT-0001')).toBeTruthy();
    expect(screen.getByText('ABCDE1234F')).toBeTruthy();
    expect(screen.getByText('194C')).toBeTruthy();
    expect(screen.getByText('TDS deducted by customers')).toBeTruthy();
  });

  it('sends the date range with the request and the export', async () => {
    getTdsReceivableReport.mockResolvedValue({ rows: [ROW], totalTds: '100.00', count: 1 });
    wrap();
    await screen.findByText('RCT-0001');
    await userEvent.type(screen.getByLabelText(/^from/i), '2026-10-01');
    await waitFor(() => expect(getTdsReceivableReport).toHaveBeenLastCalledWith({ date_from: '2026-10-01' }));
    await userEvent.click(screen.getByRole('button', { name: /export csv/i }));
    await waitFor(() => expect(exportTdsReceivableCsv).toHaveBeenCalledWith({ date_from: '2026-10-01' }));
    await waitFor(() => expect(triggerBlobDownload).toHaveBeenCalled());
  });

  it('says so when there are none, and hides the export from people who may not export', async () => {
    auth.role = 'ACCOUNTANT';
    auth.canExport = false;
    getTdsReceivableReport.mockResolvedValue({ rows: [], totalTds: '0.00', count: 0 });
    wrap();
    expect(await screen.findByText('No receipts with TDS in this range.')).toBeTruthy();
    expect(screen.queryByRole('button', { name: /export csv/i })).toBeNull();
  });
});

describe('TdsReceivablePage certificates', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    auth.role = 'OWNER';
    auth.canExport = true;
    auth.canCreatePayments = true;
  });

  it('shows which receipts are still waiting for the certificate and which have it', async () => {
    getTdsReceivableReport.mockResolvedValue({
      rows: [
        ROW,
        { ...ROW, receiptId: 2, receiptNumber: 'RCT-0002', certificateReceivedOn: '2026-10-05', certificateRef: '16A/9' },
      ],
      totalTds: '200.00',
      count: 2,
    });
    wrap();
    expect(await screen.findByText('RCT-0002')).toBeTruthy();
    expect(screen.getByText('Awaiting')).toBeTruthy();
    expect(screen.getByText('Received 2026-10-05 · 16A/9')).toBeTruthy();
  });

  it('records that the certificate arrived, with a date and a reference, and says it posts nothing', async () => {
    getTdsReceivableReport.mockResolvedValue({ rows: [ROW], totalTds: '100.00', count: 1 });
    wrap();
    await screen.findByText('RCT-0001');
    await userEvent.click(screen.getByRole('button', { name: 'Certificate received' }));
    const dialog = await screen.findByRole('dialog', { name: /TDS certificate for RCT-0001/ });
    expect(within(dialog).getByText(/posts nothing to your books/)).toBeTruthy();
    await userEvent.type(within(dialog).getByLabelText('Received on'), '2026-10-05');
    await userEvent.type(within(dialog).getByLabelText('Certificate number (optional)'), '16A/9');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Save' }));
    await waitFor(() =>
      expect(setReceiptTdsCertificate).toHaveBeenCalledWith(1, {
        id: 1, received: true, receivedOn: '2026-10-05', reference: '16A/9',
      }),
    );
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  });

  it('undoes a recorded certificate', async () => {
    getTdsReceivableReport.mockResolvedValue({
      rows: [{ ...ROW, certificateReceivedOn: '2026-10-05', certificateRef: '' }],
      totalTds: '100.00',
      count: 1,
    });
    wrap();
    await userEvent.click(await screen.findByRole('button', { name: 'Undo received' }));
    await waitFor(() => expect(setReceiptTdsCertificate).toHaveBeenCalledWith(1, { id: 1, received: false }));
  });

  it('keeps the dialog open and shows the reason when the server refuses', async () => {
    setReceiptTdsCertificate.mockRejectedValueOnce(new Error('This receipt has no TDS deducted.'));
    getTdsReceivableReport.mockResolvedValue({ rows: [ROW], totalTds: '100.00', count: 1 });
    wrap();
    await userEvent.click(await screen.findByRole('button', { name: 'Certificate received' }));
    const dialog = await screen.findByRole('dialog');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Save' }));
    expect(await within(dialog).findByText('This receipt has no TDS deducted.')).toBeTruthy();
  });

  it('offers no certificate action to someone who cannot create payments', async () => {
    auth.canCreatePayments = false;
    auth.role = 'VIEWER';
    getTdsReceivableReport.mockResolvedValue({ rows: [ROW], totalTds: '100.00', count: 1 });
    wrap();
    await screen.findByText('RCT-0001');
    expect(screen.queryByRole('button', { name: 'Certificate received' })).toBeNull();
  });

  it('opens on receipts awaiting a certificate when the Money hub sends them, and asks the server for that', async () => {
    getTdsReceivableReport.mockResolvedValue({ rows: [ROW], totalTds: '100.00', count: 1 });
    wrap('/reports/tds-receivable?certificate=pending&via=money');
    expect(await screen.findByText('Opened from Money: TDS awaiting certificate')).toBeTruthy();
    expect(getTdsReceivableReport).toHaveBeenCalledWith({ certificate: 'pending' });
    await userEvent.click(screen.getByRole('button', { name: 'Show everything' }));
    await waitFor(() => expect(getTdsReceivableReport).toHaveBeenLastCalledWith({}));
  });
});
