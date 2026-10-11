import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { TdsReceivablePage } from '@/pages/reports/TdsReceivablePage';

const { getTdsReceivableReport, exportTdsReceivableCsv, triggerBlobDownload, auth } = vi.hoisted(() => ({
  getTdsReceivableReport: vi.fn(),
  exportTdsReceivableCsv: vi.fn(async () => new Blob(['a'], { type: 'text/csv' })),
  triggerBlobDownload: vi.fn(),
  auth: { role: 'OWNER', canExport: true },
}));

vi.mock('@/api/resources', () => ({
  getTdsReceivableReport: (...args: unknown[]) => getTdsReceivableReport(...args),
  exportTdsReceivableCsv: (...args: unknown[]) => exportTdsReceivableCsv(...args),
}));
vi.mock('@/utils/blob', () => ({ triggerBlobDownload: (...args: unknown[]) => triggerBlobDownload(...args) }));
vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ user: { id: 1, email: 'o@x.test', fullName: 'O', role: auth.role, canExport: auth.canExport, companyId: 9 } }),
}));

const ROW = {
  receiptId: 1, receiptNumber: 'RCT-0001', receiptDate: '2026-10-01', customerId: 3, customer: 'Ravi Traders',
  pan: 'ABCDE1234F', section: '194C', amountReceived: '900.00', tdsDeducted: '100.00', tdsApplied: '100.00', tdsUnapplied: '0.00',
};

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
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
