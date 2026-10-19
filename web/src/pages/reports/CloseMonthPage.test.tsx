import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { CloseMonthPage } from '@/pages/reports/CloseMonthPage';

const { getReport, getGst, access } = vi.hoisted(() => ({
  getReport: vi.fn(),
  getGst: vi.fn(),
  access: { books: true, gst: true },
}));

vi.mock('@/api/resources', () => ({
  getAccountingReport: (...a: unknown[]) => getReport(...a),
  getGstHealth: (...a: unknown[]) => getGst(...a),
}));
vi.mock('@/auth/AuthContext', () => ({ useAuth: () => ({ user: { id: 1, role: 'OWNER' } }) }));
vi.mock('@/navigation/reportAccess', () => ({
  canViewAccountingReports: () => access.books,
  canViewGstrReports: () => access.gst,
}));

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <CloseMonthPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  access.books = true;
  access.gst = true;
});

describe('CloseMonthPage checklist', () => {
  it('shows every check as clear when nothing is wrong', async () => {
    getReport.mockImplementation(async (report: string) => (report === 'trial-balance' ? { balanced: true } : { alerts: [] }));
    getGst.mockResolvedValue({ summary: { critical: 0, warning: 0 }, alerts: [] });
    wrap();
    expect((await screen.findAllByText('All clear')).length).toBe(3);
  });

  it('flags an unbalanced trial balance and open GST issues', async () => {
    getReport.mockImplementation(async (report: string) => (report === 'trial-balance' ? { balanced: false } : { alerts: [{ code: 'X' }] }));
    getGst.mockResolvedValue({ summary: { critical: 1, warning: 2 }, alerts: [] });
    wrap();
    await screen.findByText('Not balanced');
    expect(screen.getByText('3 to look at')).toBeTruthy();
    expect(screen.getByText('1 to look at')).toBeTruthy();
  });

  it('says it could not check, never all clear, when a check fails', async () => {
    getReport.mockRejectedValue(new Error('down'));
    getGst.mockRejectedValue(new Error('down'));
    wrap();
    expect((await screen.findAllByText('Could not check')).length).toBe(3);
    expect(screen.queryByText('All clear')).toBeNull();
  });

  it('skips the books checks when books are off and the GST checks when GST is off', async () => {
    access.books = false;
    access.gst = false;
    wrap();
    await screen.findByText(/Books are not switched on/);
    expect(getReport).not.toHaveBeenCalled();
    expect(getGst).not.toHaveBeenCalled();
    expect(screen.queryByText('GST health for the month')).toBeNull();
  });
});
