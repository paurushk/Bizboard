import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { InventoryReportPage } from '@/pages/reports/InventoryReportPage';

const { getSummary } = vi.hoisted(() => ({ getSummary: vi.fn() }));

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ user: { id: 1, email: 'o@x.test', fullName: 'O', role: 'OWNER', companyId: 9, canExport: true } }),
}));
vi.mock('@/api/resources', () => ({
  getInventorySummary: (...a: unknown[]) => getSummary(...a),
  exportReport: vi.fn(),
}));
// A windowed table that, like the real one, shows nothing until it is measured.
vi.mock('@/components/VirtualizedTable', () => ({
  VirtualizedTable: () => <div data-testid="windowed" />,
}));

describe('Inventory print (RPT-13)', () => {
  it('prints from a full table, not the windowed one, then goes back', async () => {
    const print = vi.fn();
    Object.defineProperty(window, 'print', { value: print, configurable: true });
    getSummary.mockResolvedValue({
      rows: [
        { product: 'Widget', sku: 'W1', warehouse: 'Main', onHand: '5', reserved: '0', available: '5', reorderLevel: '1', stockValue: '50', status: 'OK' },
        { product: 'Gadget', sku: 'G1', warehouse: 'Main', onHand: '2', reserved: '0', available: '2', reorderLevel: '1', stockValue: '20', status: 'OK' },
      ],
    });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <InventoryReportPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    await screen.findByTestId('windowed');
    expect(screen.queryByText('Gadget')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: /print/i }));
    await waitFor(() => expect(print).toHaveBeenCalled());
    expect(screen.getByText('Gadget')).toBeTruthy();
    expect(screen.getByText('Widget')).toBeTruthy();

    act(() => {
      window.dispatchEvent(new Event('afterprint'));
    });
    await screen.findByTestId('windowed');
  });
});
