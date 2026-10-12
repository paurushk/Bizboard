import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { SalesOrdersPage } from '@/pages/sales/SalesOrdersPage';

let currentUser: Record<string, unknown> = { id: 1, role: 'STAFF', companyId: 1, canCreateSales: true };

vi.mock('@/auth/AuthContext', () => ({ useAuth: () => ({ user: currentUser }) }));
vi.mock('@/api/resources', () => ({
  listSalesOrdersPage: async () => ({ results: [], count: 0, next: null, previous: null }),
  convertSalesOrder: vi.fn(),
  convertSalesOrderToChallan: vi.fn(),
  cancelSalesOrder: vi.fn(),
  createDeliveryRoute: vi.fn(),
}));
vi.mock('@/api/osPlan', () => ({
  checkSalesOrderGate: vi.fn(),
  confirmSalesOrder: vi.fn(),
}));

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <SalesOrdersPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('SalesOrdersPage — Quick Entry shortcut', () => {
  it('links to Quick Entry for a user who can create sales', async () => {
    currentUser = { id: 1, role: 'STAFF', companyId: 1, canCreateSales: true };
    renderPage();
    expect(await screen.findByRole('link', { name: 'Quick entry' })).toHaveAttribute('href', '/sales/quick-entry');
  });

  it('hides it from a user who cannot', async () => {
    currentUser = { id: 2, role: 'VIEWER', companyId: 1, canCreateSales: false };
    renderPage();
    await screen.findAllByRole('heading');
    expect(screen.queryByRole('link', { name: 'Quick entry' })).toBeNull();
  });
});
