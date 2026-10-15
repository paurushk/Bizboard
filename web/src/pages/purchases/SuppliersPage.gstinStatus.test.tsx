import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { SuppliersPage } from '@/pages/purchases/SuppliersPage';

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ user: { id: 1, email: 'o@x.test', fullName: 'Owner', role: 'OWNER', companyId: 9 } }),
}));

vi.mock('@/api/resources', () => ({
  listSuppliersPage: async () => ({ count: 3, next: null, previous: null, results: [
    { id: 1, name: 'Valid Vendor', gstin: '29ABCDE1234F1ZW', gstinVerificationStatus: 'VALID', state: 'Karnataka', isActive: true },
    { id: 2, name: 'Cancelled Vendor', gstin: '27AABCU9603R1ZN', gstinVerificationStatus: 'CANCELLED', state: 'Maharashtra', isActive: true },
    { id: 3, name: 'Fresh Vendor', gstin: '07AAAAA0000A1Z5', gstinVerificationStatus: 'UNVERIFIED', state: 'Delhi', isActive: true },
  ] }),
  getCompany: async () => ({ id: 1, name: 'Shop', isGstRegistered: false }),
  createSupplier: vi.fn(),
  updateSupplier: vi.fn(),
  verifySupplierGstin: vi.fn(),
  getSupplierPriceHistory: vi.fn(),
}));

function chipFor(name: string) {
  const row = screen.getByText(name).closest('tr')!;
  return within(row).getAllByText(/Verified|Cancelled|Unverified/).map((el) => el.closest('.MuiChip-root')!).find(Boolean)!;
}

describe('SuppliersPage GSTIN status chips', () => {
  it('colour the status the API stores, the same way the Customers list does', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <SuppliersPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    await screen.findByText('Valid Vendor');
    expect(chipFor('Valid Vendor').className).toContain('colorSuccess');
    expect(chipFor('Cancelled Vendor').className).toContain('colorError');
    expect(chipFor('Fresh Vendor').className).toContain('colorWarning');
  });
});
