import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactElement, ReactNode } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { setLocale, t } from '@/i18n';
import { InventoryReportPage } from '@/pages/reports/InventoryReportPage';

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 1, email: 'owner@x.test', fullName: 'Owner', role: 'OWNER', companyId: 9, canExport: true },
  }),
}));

vi.mock('@/api/resources', () => ({
  getInventorySummary: vi.fn(),
  exportReport: vi.fn(),
}));

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
    const rows = Array.from({ length: count }, (_, index) => ({
      index,
      start: index * 52,
      end: (index + 1) * 52,
      size: 52,
    }));
    return children({ rows, totalSize: count * 52, measureElement: () => {} });
  },
}));

function wrap(ui: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('InventoryReportPage Hindi columns', () => {
  afterEach(() => setLocale('en'));

  it('uses Hindi column headings and the drift note, and downloads a CSV instead of mailing a link', async () => {
    setLocale('hi');
    const { getInventorySummary, exportReport } = await import('@/api/resources');
    vi.mocked(getInventorySummary).mockResolvedValue({
      rows: [{
        product: 'Rice',
        sku: 'RICE',
        warehouse: 'Main',
        onHand: 10,
        reserved: 2,
        available: 8,
        reorderLevel: 1,
        stockValue: 100,
        balanceDrift: true,
        balanceOnHand: 4,
      }],
    } as never);
    vi.mocked(exportReport).mockResolvedValue({ url: 'https://files.test/inventory.csv' });
    const hrefs: string[] = [];
    const realLocation = window.location;
    const fakeLocation = { assign: () => undefined, replace: () => undefined, reload: () => undefined };
    Object.defineProperty(fakeLocation, 'href', {
      get: () => hrefs.at(-1) ?? '',
      set: (value: string) => {
        hrefs.push(value);
      },
    });
    Object.defineProperty(window, 'location', { configurable: true, value: fakeLocation });
    const anchorClick = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});

    try {
      wrap(<InventoryReportPage />);
      expect(await screen.findByText(t('cog.colReserved'))).toBeTruthy();
      expect(screen.getByText(t('cog.colAvailable'))).toBeTruthy();
      expect(screen.getByText(t('cog.colStockValue'))).toBeTruthy();
      expect(screen.queryByRole('columnheader', { name: 'Reserved' })).toBeNull();

      await userEvent.hover(screen.getByText(t('sweep.balanceDrift')));
      expect(await screen.findByRole('tooltip')).toHaveTextContent(t('cog.cacheDrift', { qty: '4' }));

      // INV-WP-11: the old "email" button mailed a blob: link that only works in this tab. Gone.
      expect(screen.queryByRole('button', { name: t('reports.emailExcel') })).toBeNull();
      await userEvent.click(screen.getByRole('button', { name: t('inventory.downloadCsv') }));
      await waitFor(() => expect(anchorClick).toHaveBeenCalled());
      expect(hrefs.some((value) => value.startsWith('mailto:'))).toBe(false);
    } finally {
      anchorClick.mockRestore();
      Object.defineProperty(window, 'location', { configurable: true, value: realLocation });
    }
  });
});
