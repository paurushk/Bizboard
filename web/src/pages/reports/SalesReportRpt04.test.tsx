import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { SalesReportPage } from '@/pages/reports/SalesReportPage';

const { getRegister, getSummary } = vi.hoisted(() => ({ getRegister: vi.fn(), getSummary: vi.fn() }));

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ user: { id: 1, email: 'o@x.test', fullName: 'O', role: 'OWNER', companyId: 9 } }),
}));
vi.mock('@/api/resources', () => ({
  getSalesRegister: (...a: unknown[]) => getRegister(...a),
  getSalesSummary: (...a: unknown[]) => getSummary(...a),
  exportReport: vi.fn(),
}));

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <SalesReportPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const SUMMARY = {
  totals: {
    revenue: '1180.00', invoiceCount: 2, grossInvoiced: '1416.00', creditNotes: '236.00', debitNotes: '0.00',
    taxable: '1000.00', gstAndOther: '180.00',
  },
  topCustomers: [], topProducts: [], byDate: [],
};

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  getRegister.mockResolvedValue({ rows: [] });
});

describe('Sales summary (RPT-04)', () => {
  it('shows sales incl. GST net of credit notes with the breakdown', async () => {
    getSummary.mockResolvedValue(SUMMARY);
    wrap();
    await screen.findByText('Sales incl. GST (net of credit notes)');
    const card = screen.getByText('Sales incl. GST (net of credit notes)').closest('.MuiPaper-root');
    expect(card?.textContent).toMatch(/1,180/);
    expect(card?.textContent).toMatch(/Credit notes/);
    expect(card?.textContent).toMatch(/Before GST/);
    expect(screen.getByText('Compare with GSTR-1')).toBeTruthy();
  });

  it('shows the error, not stale or zero figures, when the summary fails', async () => {
    getSummary.mockRejectedValue(new Error('summary down'));
    wrap();
    await screen.findByText(/summary down/);
    expect(screen.queryByText('Sales incl. GST (net of credit notes)')).toBeNull();
  });

  it('opens on a bounded range and stops asking when the range runs backwards', async () => {
    getSummary.mockResolvedValue(SUMMARY);
    wrap();
    await screen.findByText('Sales incl. GST (net of credit notes)');
    expect(getSummary.mock.calls[0][0].date_from).toMatch(/^\d{4}-04-01$/);
    const calls = getSummary.mock.calls.length;
    fireEvent.change(screen.getByLabelText('From'), { target: { value: '2999-01-01' } });
    await screen.findByText('From must be on or before To.');
    await waitFor(() => expect(getSummary.mock.calls.length).toBe(calls));
  });
});
