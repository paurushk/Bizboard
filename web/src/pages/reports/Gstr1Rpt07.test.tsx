import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { Gstr1ReportPage } from '@/pages/reports/GstReturnPage';

vi.mock('@/api/resources', () => ({
  getGstReturn: async () => ({
    totals: { outward_taxable: '1000.00' },
    b2b: [{ invoice_number: 'INV-1', invoice_date: '2026-07-15', ctin: '29AAAAA0000A1Z5', taxable_value: '1000.00' }],
    b2cl: [], b2cs: [], cdnr: [{ note_kind: 'CREDIT', note_number: 'CN-1', note_date: '2026-07-20', taxable_value: '200.00' }],
    document_ids: { sales_invoice: { 'INV-1': 7 }, sales_credit_note: { 'CN-1': 8 }, sales_debit_note: {} },
    issues: [],
  }),
  listGstSnapshots: async () => [
    { id: 1, returnType: 'GSTR1', period: '2026-07', contentHash: 'abc123def456', builderVersion: 'v9', generatedAt: '2026-08-01T10:15:00Z', generatedBy: 'Asha' },
  ],
  downloadGstReturn: vi.fn(),
  downloadGstCaPack: vi.fn(),
  getCmp08: vi.fn(),
  getGstr4: vi.fn(),
  getCompany: async () => ({ registrationType: 'REGULAR' }),
  listCompanyGstins: async () => [],
}));
vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ user: { id: 1, email: 'o@x.test', fullName: 'O', role: 'OWNER', canExport: true, companyId: 9, company: { registrationType: 'REGULAR' } } }),
}));
// show every row (the real windowed table needs layout)
vi.mock('@/components/VirtualizedTable', () => ({
  VirtualizedTable: ({ rowCount, children }: { rowCount?: number; children: (a: { rows: { index: number; start: number; end: number; size: number }[]; totalSize: number; measureElement: () => void }) => ReactNode }) =>
    children({ rows: Array.from({ length: rowCount ?? 0 }, (_, index) => ({ index, start: index * 52, end: (index + 1) * 52, size: 52 })), totalSize: 0, measureElement: () => {} }),
}));

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <Gstr1ReportPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('GSTR-1 page rows and snapshots (RPT-07)', () => {
  it('lists the B2B and note rows with a link to each document', async () => {
    wrap();
    fireEvent.click(await screen.findByText(/Sales to registered buyers \(B2B\)/));
    const invoice = await screen.findByRole('link', { name: 'INV-1' });
    expect(invoice.getAttribute('href')).toBe('/sales/history/7');
    fireEvent.click(screen.getByText(/Credit and debit notes \(registered buyers\)/));
    const note = await screen.findByRole('link', { name: 'CN-1' });
    expect(note.getAttribute('href')).toBe('/sales/credit-notes/8');
  });

  it('lists the saved snapshots', async () => {
    wrap();
    fireEvent.click(await screen.findByText(/Saved snapshots/));
    await screen.findByText('Asha');
    expect(screen.getByText('abc123def456')).toBeTruthy();
    expect(screen.getByText('2026-08-01 10:15')).toBeTruthy();
  });
});
