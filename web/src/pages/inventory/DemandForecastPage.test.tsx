import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { DemandForecastPage } from '@/pages/inventory/DemandForecastPage';

const { getDemandForecast } = vi.hoisted(() => ({
  getDemandForecast: vi.fn(),
}));

vi.mock('@/api/osPlan', () => ({
  getDemandForecast: () => getDemandForecast(),
}));

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/inventory/demand-forecast']}>
        <Routes>
          <Route path="/inventory/demand-forecast" element={<DemandForecastPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('DemandForecastPage', () => {
  it('renders forecast rows when data is returned', async () => {
    getDemandForecast.mockResolvedValueOnce({
      rows: [
        {
          productId: 101,
          productName: '50kg Wheat Flour',
          soldQty: '120.000',
          dailyRate: '4.000',
          method: 'moving_average',
          windowDays: 30,
        },
      ],
    });

    renderPage();

    await waitFor(() => {
      expect(screen.getByText('50kg Wheat Flour')).toBeInTheDocument();
    });

    expect(screen.getByText('120.000')).toBeInTheDocument();
    expect(screen.getByText('4.000')).toBeInTheDocument();
    expect(screen.getByText(/Moving average · 30/)).toBeInTheDocument();
  });

  it('renders empty forecast message when no rows are available', async () => {
    getDemandForecast.mockResolvedValueOnce({ rows: [] });

    renderPage();

    await waitFor(() => {
      expect(screen.getByText('No posted sales in the last 30 days.')).toBeInTheDocument();
    });

    expect(screen.queryByRole('table')).not.toBeInTheDocument();
    expect(screen.queryByText('50kg Wheat Flour')).not.toBeInTheDocument();
  });

  it('shows an error and hides the table when the forecast fails', async () => {
    getDemandForecast.mockRejectedValueOnce(new Error('offline'));
    renderPage();
    expect(await screen.findByText('offline')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });

  it('puts what needs ordering first, with cover and a suggested quantity, and links it to an order', async () => {
    getDemandForecast.mockResolvedValueOnce({
      rows: [
        {
          productId: 1, productName: 'Fast tea', soldQty: '60.000', dailyRate: '2.000', method: 'trailing_mean_net',
          windowDays: 30, unit: 'pcs', available: '40.000', onOrder: '0.000', daysOfCover: 20, suggestedQty: '20.000',
          needsAction: true, supplierId: 5, supplierName: 'Mega Suppliers',
        },
        {
          productId: 2, productName: 'Slow rice', soldQty: '30.000', dailyRate: '1.000', method: 'trailing_mean_net',
          windowDays: 30, available: '970.000', onOrder: '0.000', daysOfCover: 970, suggestedQty: '0.000', needsAction: false,
        },
      ],
    });
    const user = userEvent.setup();
    renderPage();
    expect(await screen.findByText('Fast tea')).toBeInTheDocument();
    expect(screen.queryByText('Slow rice')).not.toBeInTheDocument();
    expect(screen.getByText('20 pcs')).toBeInTheDocument();
    expect(screen.getByText('Mega Suppliers')).toBeInTheDocument();
    const link = screen.getByRole('link', { name: /Fast tea/ });
    expect(link.getAttribute('href')).toBe('/purchases/orders/new?product=1&qty=20&supplier=5');
    await user.click(screen.getByRole('tab', { name: 'All sellers (2)' }));
    expect(await screen.findByText('Slow rice')).toBeInTheDocument();
  });

  it('says so when nothing needs ordering', async () => {
    getDemandForecast.mockResolvedValueOnce({
      rows: [{ productId: 2, productName: 'Slow rice', soldQty: '30', dailyRate: '1', method: 'trailing_mean_net', windowDays: 30, needsAction: false }],
    });
    renderPage();
    expect(await screen.findByText(/Nothing needs ordering right now/)).toBeInTheDocument();
  });
  it('searches the list, shows the not-moving items on their own tab and names the in-stock days', async () => {
    getDemandForecast.mockResolvedValueOnce({
      rows: [
        {
          productId: 1, productName: 'Fast tea', soldQty: '20.000', dailyRate: '2.000', method: 'in_stock_days_mean',
          windowDays: 30, inStockDays: 10, available: '5.000', onOrder: '0.000', daysOfCover: 2, suggestedQty: '55.000', needsAction: true,
        },
        {
          productId: 2, productName: 'Brown rice', soldQty: '30.000', dailyRate: '1.000', method: 'trailing_mean_net',
          windowDays: 30, available: '3.000', onOrder: '0.000', daysOfCover: 3, suggestedQty: '27.000', needsAction: true,
        },
      ],
      overstock: [
        { productId: 9, productName: 'Old stock', unit: 'pcs', available: '500.000', dailyRate: '0.000', daysOfCover: null, noSales: true, lookbackDays: 90 },
      ],
    });
    const user = userEvent.setup();
    renderPage();
    expect(await screen.findByText('Fast tea')).toBeInTheDocument();
    expect(screen.getByText(/over 10 of 30 days in stock/)).toBeInTheDocument();
    await user.type(screen.getByLabelText('Search item'), 'rice');
    expect(screen.queryByText('Fast tea')).not.toBeInTheDocument();
    expect(screen.getByText('Brown rice')).toBeInTheDocument();
    await user.clear(screen.getByLabelText('Search item'));
    await user.click(screen.getByRole('tab', { name: 'Not moving (1)' }));
    expect(await screen.findByText('Old stock')).toBeInTheDocument();
    expect(screen.getByText('No sales in 90 days')).toBeInTheDocument();
    expect(screen.queryByText('Fast tea')).not.toBeInTheDocument();
  });

  it('downloads what is on screen as a spreadsheet file', async () => {
    getDemandForecast.mockResolvedValueOnce({
      rows: [
        {
          productId: 1, productName: 'Fast tea', soldQty: '20.000', dailyRate: '2.000', method: 'trailing_mean_net',
          windowDays: 30, available: '5.000', onOrder: '0.000', daysOfCover: 2, suggestedQty: '55.000', needsAction: true,
        },
      ],
    });
    let saved = '';
    const OriginalBlob = globalThis.Blob;
    vi.spyOn(globalThis, 'Blob').mockImplementation(function (parts?: BlobPart[], options?: BlobPropertyBag) {
      saved = String(parts?.[0] ?? '');
      return new OriginalBlob(parts, options);
    } as never);
    URL.createObjectURL = vi.fn(() => 'blob:x');
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Fast tea');
    await user.click(screen.getByRole('button', { name: 'Download CSV' }));
    expect(saved).toContain('"Product","Sold"');
    expect(saved).toContain('"Fast tea","20.000","2.000"');
  });
});
