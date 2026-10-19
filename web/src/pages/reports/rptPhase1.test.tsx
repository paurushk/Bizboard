import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { GstRateExposurePage } from '@/pages/reports/GstRateExposurePage';
import { Gstr2bPage } from '@/pages/reports/Gstr2bPage';
import { StatutoryEventsPage } from '@/pages/reports/StatutoryEventsPage';
import { TdsTcsReportsPage } from '@/pages/reports/TdsTcsReportsPage';

const { apiGet, listStatutory, listGstr2b, preview, auth } = vi.hoisted(() => ({
  apiGet: vi.fn(),
  listStatutory: vi.fn(),
  listGstr2b: vi.fn(),
  preview: vi.fn(),
  auth: { role: 'ACCOUNTANT', canExport: false },
}));

vi.mock('@/api/client', async () => {
  const actual = await vi.importActual<typeof import('@/api/client')>('@/api/client');
  return { ...actual, apiClient: { ...actual.apiClient, get: (...a: unknown[]) => apiGet(...a) } };
});
vi.mock('@/api/statutory', () => ({ listStatutoryEventsPage: (...a: unknown[]) => listStatutory(...a) }));
vi.mock('@/api/gstr2b', async () => {
  const actual = await vi.importActual<typeof import('@/api/gstr2b')>('@/api/gstr2b');
  return {
    ...actual,
    listGstr2bPage: (...a: unknown[]) => listGstr2b(...a),
    fetchImsSummary: vi.fn(async () => ({})),
    fetchImsScorecard: vi.fn(async () => ({ period: '2026-09', suppliers: [] })),
  };
});
vi.mock('@/api/resources', async () => {
  const actual = await vi.importActual<typeof import('@/api/resources')>('@/api/resources');
  return { ...actual, getTaxWorksheetPreview: (...a: unknown[]) => preview(...a) };
});
vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ user: { id: 1, email: 'a@x.test', fullName: 'A', role: auth.role, canExport: auth.canExport, companyId: 9 } }),
}));

function wrap(node: JSX.Element) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{node}</MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  auth.role = 'ACCOUNTANT';
  auth.canExport = false;
});

describe('RPT-02 failed loads never read as "nothing found"', () => {
  it('rate back-scan', async () => {
    apiGet.mockRejectedValue(new Error('boom'));
    wrap(<GstRateExposurePage />);
    await screen.findByText(/boom/);
    expect(screen.queryByText(/no rate mismatches|nothing/i)).toBeNull();
    expect(document.body.textContent).not.toMatch(/No rate/i);
  });

  it('GSTR-2B', async () => {
    listGstr2b.mockRejectedValue(new Error('2b down'));
    wrap(<Gstr2bPage />);
    await screen.findByText(/2b down/);
    expect(screen.queryByText(/nothing here yet|no data/i)).toBeNull();
  });

  it('statutory events', async () => {
    listStatutory.mockRejectedValue(new Error('events down'));
    wrap(<StatutoryEventsPage />);
    await screen.findByText(/events down/);
    expect(screen.queryByText(/nothing here yet|no data/i)).toBeNull();
  });
});

describe('RPT-03 TDS/TCS worksheet page', () => {
  const data = {
    kind: 'tds', period: '2026-08', disclaimer: 'x', count: 1,
    rows: [{ date: '2026-08-05', invoice: 'PI-1', supplier: 'Acme', section: '194C', rate: '1', taxable: '1000.00', tds_amount: '10.00' }],
    bySection: [{ section: '194C', count: 1, taxable: '1000.00', amount: '10.00' }],
    totals: { taxable: '1000.00', amount: '10.00' },
  };

  it('previews for an accountant without export rights, and hides the download', async () => {
    preview.mockResolvedValue(data);
    wrap(<TdsTcsReportsPage />);
    await screen.findByText('PI-1');
    expect(screen.queryByRole('button', { name: /download 26q/i })).toBeNull();
    expect(screen.getAllByText(/export rights/i).length).toBeGreaterThan(0);
  });

  it('offers the download to someone who can export', async () => {
    auth.canExport = true;
    preview.mockResolvedValue(data);
    wrap(<TdsTcsReportsPage />);
    await screen.findByText('PI-1');
    expect(screen.getByRole('button', { name: /download 26q/i })).toBeTruthy();
  });

  it('shows the server message when the preview fails', async () => {
    preview.mockRejectedValue(new Error('TDS/TCS is not switched on for this company'));
    wrap(<TdsTcsReportsPage />);
    await waitFor(() => expect(document.body.textContent).toMatch(/not switched on/));
  });

  it('says so when the month has no entries', async () => {
    preview.mockResolvedValue({ ...data, count: 0, rows: [], bySection: [], totals: { taxable: '0', amount: '0' } });
    wrap(<TdsTcsReportsPage />);
    await screen.findByText(/No TDS or TCS entries/);
  });
});
