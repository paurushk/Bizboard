import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
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
    expect(screen.getByText(/moving_average · 30/)).toBeInTheDocument();
  });

  it('renders empty forecast message when no rows are available', async () => {
    getDemandForecast.mockResolvedValueOnce({ rows: [] });

    renderPage();

    await waitFor(() => {
      expect(screen.getByRole('table')).toBeInTheDocument();
    });

    expect(screen.queryByText('50kg Wheat Flour')).not.toBeInTheDocument();
  });
});
