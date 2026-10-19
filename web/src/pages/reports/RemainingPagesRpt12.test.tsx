import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { Gstr9ReportPage } from '@/pages/reports/Gstr9ReportPage';
import { MissingDocumentsPage } from '@/pages/reports/MissingDocumentsPage';

const { fetchMissing, getGstr9 } = vi.hoisted(() => ({ fetchMissing: vi.fn(), getGstr9: vi.fn() }));

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ user: { id: 1, email: 'o@x.test', fullName: 'O', role: 'OWNER', companyId: 1 } }),
}));
vi.mock('@/components/GstHonestyHeader', () => ({ GstHonestyHeader: () => null }));
// The real windowed table shows nothing in jsdom (no layout), so show every row.
vi.mock('@/components/VirtualizedTable', () => ({
  VirtualizedTable: ({
    rowCount,
    children,
  }: {
    rowCount?: number;
    children: (args: {
      rows: { index: number; start: number; end: number; size: number }[];
      totalSize: number;
      measureElement: () => void;
    }) => ReactNode;
  }) => {
    const count = rowCount ?? 0;
    const rows = Array.from({ length: count }, (_, index) => ({ index, start: index * 52, end: (index + 1) * 52, size: 52 }));
    return children({ rows, totalSize: count * 52, measureElement: () => {} });
  },
}));
vi.mock('@/api/gstr2b', () => ({
  fetchMissingDocuments: (...a: unknown[]) => fetchMissing(...a),
  chaseMissingWhatsApp: vi.fn(),
  chaseMissingPhoto: vi.fn(),
}));
vi.mock('@/api/resources', () => ({
  getGstr9: (...a: unknown[]) => getGstr9(...a),
  downloadGstr9: vi.fn(),
  getGstr9FilingDate: async (fy: string) => ({ fy, filedOn: null, noteDeadline: '2026-11-30' }),
  setGstr9FilingDate: vi.fn(),
}));

function wrap(node: JSX.Element) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{node}</MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => vi.clearAllMocks());

describe('Missing bills (RPT-12)', () => {
  const item = { id: 1, supplier_gstin: '29AAAAA0000A1Z5', invoice_number: 'INV-9', invoice_date: '2026-09-02', taxable_value: '1000', status: 'MISSING' };

  it('keeps the month picker on screen while another month loads', async () => {
    fetchMissing.mockResolvedValueOnce({ items: [item] });
    wrap(<MissingDocumentsPage />);
    await screen.findByText('INV-9');
    fetchMissing.mockReturnValue(new Promise(() => {}));
    const month = screen.getByLabelText(/period|month/i) as HTMLInputElement;
    fireEvent.change(month, { target: { value: '2026-05' } });
    await waitFor(() => expect(fetchMissing).toHaveBeenCalledTimes(2));
    expect(screen.getByLabelText(/period|month/i)).toBeTruthy();
    expect(screen.getByText('INV-9')).toBeTruthy();
  });

  it('shows the error, never "nothing missing", when the list fails to load', async () => {
    fetchMissing.mockRejectedValue(new Error('list down'));
    wrap(<MissingDocumentsPage />);
    await screen.findByText(/list down/);
    expect(screen.queryByText(/nothing|no missing|all matched/i)).toBeNull();
    expect(screen.getByLabelText(/period|month/i)).toBeTruthy();
  });

  it('shows the taxable value as money', async () => {
    fetchMissing.mockResolvedValue({ items: [item] });
    wrap(<MissingDocumentsPage />);
    await screen.findByText('INV-9');
    expect(document.body.textContent).toMatch(/1,000\.00/);
  });
});

describe('GSTR-9 (RPT-12)', () => {
  it('asks the server only once the year looks complete', async () => {
    getGstr9.mockResolvedValue({ annual: {}, tables: {} });
    wrap(<Gstr9ReportPage />);
    await waitFor(() => expect(getGstr9).toHaveBeenCalledTimes(1));
    const fy = screen.getByLabelText(/financial year/i);
    fireEvent.change(fy, { target: { value: '2025-2' } });
    fireEvent.change(fy, { target: { value: '2025' } });
    await new Promise((r) => setTimeout(r, 50));
    expect(getGstr9).toHaveBeenCalledTimes(1);
    fireEvent.change(fy, { target: { value: '2024-25' } });
    await waitFor(() => expect(getGstr9).toHaveBeenCalledTimes(2));
  });
});
