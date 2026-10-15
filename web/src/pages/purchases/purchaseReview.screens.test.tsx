import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { BillsOfEntryPage } from '@/pages/purchases/BillsOfEntryPage';
import { SuppliersPage } from '@/pages/purchases/SuppliersPage';
import { registerGlobalConfirm } from '@/utils/confirmBridge';

// Purchase review WP-12: the smaller purchase screens, where an irreversible step used to be one click
// and a successful check said nothing.

const api = vi.hoisted(() => ({
  listBillsOfEntryPage: vi.fn(),
  listSuppliersPage: vi.fn(),
  completeBillOfEntry: vi.fn(),
  cancelBillOfEntry: vi.fn(),
  createBillOfEntry: vi.fn(),
  listSuppliers: vi.fn(),
  getCompany: vi.fn(),
  createSupplier: vi.fn(),
  updateSupplier: vi.fn(),
  verifySupplierGstin: vi.fn(),
  getSupplierPriceHistory: vi.fn(),
}));

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ user: { id: 1, email: 'o@x.test', fullName: 'Owner', role: 'OWNER', companyId: 9 } }),
}));
vi.mock('@/hooks/useSubscriptionGate', () => ({
  useSubscriptionGate: () => ({ writesBlocked: false, isLoading: false }),
}));
vi.mock('@/api/resources', () => api);

function mount(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  registerGlobalConfirm(null);
  vi.clearAllMocks();
});

describe('BillsOfEntryPage completing', () => {
  function setup() {
    api.listBillsOfEntryPage.mockResolvedValue({
      results: [{ id: 4, boeNumber: 'BOE-4', boeDate: '2026-10-01', supplierName: 'Port Supplies', igstAmount: '900', status: 'DRAFT' }],
    });
    api.listSuppliersPage.mockResolvedValue({ results: [] });
    api.completeBillOfEntry.mockResolvedValue({ id: 4, status: 'COMPLETED' });
  }

  it('asks first, naming the tax credit it creates', async () => {
    setup();
    const ask = vi.fn().mockResolvedValue(true);
    registerGlobalConfirm(ask);
    mount(<BillsOfEntryPage />);
    await userEvent.click(await screen.findByRole('button', { name: /^complete$/i }));
    await waitFor(() => expect(api.completeBillOfEntry).toHaveBeenCalledWith(4));
    expect(ask.mock.calls[0][0][0]).toMatch(/input tax credit/i);
  });

  it('does nothing when the confirmation is declined', async () => {
    setup();
    registerGlobalConfirm(vi.fn().mockResolvedValue(false));
    mount(<BillsOfEntryPage />);
    await userEvent.click(await screen.findByRole('button', { name: /^complete$/i }));
    await new Promise((r) => setTimeout(r, 50));
    expect(api.completeBillOfEntry).not.toHaveBeenCalled();
  });
});

describe('SuppliersPage GSTIN check', () => {
  it('says the check ran instead of changing silently', async () => {
    api.listSuppliers.mockResolvedValue([
      { id: 1, name: 'Fresh Vendor', gstin: '07AAAAA0000A1Z5', gstinVerificationStatus: 'UNVERIFIED', state: 'Delhi', isActive: true },
    ]);
    api.getCompany.mockResolvedValue({ id: 1, name: 'Shop', isGstRegistered: false });
    api.verifySupplierGstin.mockResolvedValue({});
    mount(<SuppliersPage />);
    const row = (await screen.findByText('Fresh Vendor')).closest('tr')!;
    await userEvent.click(within(row).getByRole('button', { name: /verify/i }));
    expect(await screen.findByText(/gstin check done/i)).toBeInTheDocument();
    expect(api.verifySupplierGstin).toHaveBeenCalledWith(1);
  });
});
