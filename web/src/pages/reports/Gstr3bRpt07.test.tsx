import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { Gstr3bReportPage } from '@/pages/reports/GstReturnPage';

const { getGstReturn, downloadGstReturn, auth } = vi.hoisted(() => ({
  getGstReturn: vi.fn(),
  downloadGstReturn: vi.fn(),
  auth: { canExport: true },
}));

vi.mock('@/api/resources', () => ({
  getGstReturn: (...a: unknown[]) => getGstReturn(...a),
  downloadGstReturn: (...a: unknown[]) => downloadGstReturn(...a),
  downloadGstCaPack: vi.fn(),
  listGstSnapshots: async () => [],
  getCmp08: vi.fn(),
  getGstr4: vi.fn(),
  getCompany: async () => ({ registrationType: 'REGULAR' }),
  listCompanyGstins: async () => [],
}));
vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 1, email: 'a@x.test', fullName: 'A', role: auth.canExport ? 'OWNER' : 'ACCOUNTANT', canExport: auth.canExport, companyId: 9, company: { registrationType: 'REGULAR' } },
  }),
}));

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <Gstr3bReportPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const issue = (i: number, code = 'HSN_MISSING') => ({
  code, severity: i % 2 ? 'critical' : 'warning', document_type: 'sales_invoice', document_id: 100 + i, number: `INV-${i}`,
  message: `Line ${i}: problem`,
});

const PAYLOAD = {
  outward_supplies: { igst: '0.00', cgst: '90.00', sgst: '90.00', cess: '10.00', taxable_value: '1000' },
  inward_supplies: { reverse_charge: { igst: '0.00', cgst: '9.00', sgst: '9.00', cess: '2.00' } },
  itc: {
    recommended_claimable: { igst: '0', cgst: '40.00', sgst: '40.00', cess: '0', basis: 'min(books, gstr2b_matched)' },
    books_itc: { igst: '0', cgst: '50.00', sgst: '50.00', cess: '0' },
    reversed_ineligible: {
      reversed: { count: 1, igst: '0', cgst: '9.00', sgst: '9.00', cess: '0', total_tax: '18.00' },
      ineligible: { count: 2, igst: '5.00', cgst: '0', sgst: '0', cess: '0', total_tax: '5.00' },
      needs_ca_confirmation: true,
      gstr2b_flagged: { count: 0 },
    },
  },
  tax_payable_summary: { net_payable_hint: '102.00' },
  issues: Array.from({ length: 13 }, (_, i) => issue(i)),
};

beforeEach(() => {
  vi.clearAllMocks();
  auth.canExport = true;
  getGstReturn.mockResolvedValue(PAYLOAD);
});

describe('GSTR-3B page (RPT-07)', () => {
  it('shows the backend net payable, not a client-side sum', async () => {
    wrap();
    const heading = await screen.findByText(/worksheet/i, { selector: 'h6, .MuiTypography-subtitle1' });
    const card = heading.closest('.MuiPaper-root');
    expect(card?.textContent).toMatch(/102/);
    expect(card?.textContent).not.toMatch(/130/);
  });

  it('shows 4(B) reversed and ineligible ITC with the CA flag', async () => {
    wrap();
    const block = await screen.findByTestId('itc-4b');
    expect(block.textContent).toMatch(/Table 4\(B\)/);
    expect(block.textContent).toMatch(/Your CA to confirm/);
    expect(block.textContent).toMatch(/18/);
    expect(block.textContent).toMatch(/23/);
  });

  it('lists every issue across pages, worst first, each linking to its document', async () => {
    wrap();
    await screen.findByText(/Issues/i, { selector: 'strong' });
    expect(screen.getAllByRole('link').filter((l) => l.getAttribute('href')?.startsWith('/sales/history/')).length).toBe(10);
    fireEvent.click(screen.getByLabelText('Go to next page'));
    await waitFor(() =>
      expect(screen.getAllByRole('link').filter((l) => l.getAttribute('href')?.startsWith('/sales/history/')).length).toBe(3),
    );
  });

  it('offers GSTN JSON with a note, and saves a snapshot on request', async () => {
    wrap();
    await screen.findByTestId('itc-4b');
    fireEvent.click(screen.getByRole('button', { name: 'Save snapshot' }));
    await waitFor(() => expect(getGstReturn).toHaveBeenCalledWith('gstr3b', expect.objectContaining({ persist: true })));
    await screen.findByText(/Snapshot saved/);
  });

  it('hides the file and snapshot buttons without export rights', async () => {
    auth.canExport = false;
    wrap();
    await screen.findByTestId('itc-4b');
    expect(screen.queryByRole('button', { name: 'Save snapshot' })).toBeNull();
  });
});
