import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import type { ReactElement } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import axe from 'axe-core';
import { CustomersPage } from '@/pages/sales/CustomersPage';

// The form is large and typing re-renders it per key; leave headroom for a loaded full-suite run.
vi.setConfig({ testTimeout: 90_000 });

const G_KA = '29ABCDE1234F1ZW';
const G_MH = '27AABCU9603R1ZN';

const listCustomersPage = vi.fn();
const createCustomer = vi.fn();
const updateCustomer = vi.fn();
const verifyCustomerGstin = vi.fn();
const verifyCustomersGstinBulk = vi.fn();
const lookupCustomerGstin = vi.fn();
const deleteCustomer = vi.fn();
const setPosWalkInCustomer = vi.fn();
const exportCustomersCsv = vi.fn();
const getCustomer = vi.fn();
const getCustomersSummary = vi.fn();
const getCustomersHealth = vi.fn();

const OWNER = { id: 1, email: 'o@x.test', fullName: 'Owner', role: 'OWNER', companyId: 9 };
let currentUser: Record<string, unknown> = OWNER;
let writesBlocked = false;

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ user: currentUser, isAuthenticated: true }),
}));
vi.mock('@/hooks/useSubscriptionGate', () => ({
  useSubscriptionGate: () => ({ writesBlocked, isLoading: false }),
}));
vi.mock('@/utils/blob', () => ({ triggerBlobDownload: vi.fn() }));

vi.mock('@/api/resources', () => ({
  listCustomersPage: (...args: unknown[]) => listCustomersPage(...args),
  getCompany: async () => ({ id: 9, name: 'Shop', partyCustomFieldDefs: [{ key: 'dl', label: 'Drug licence', active: true }] }),
  createCustomer: (...args: unknown[]) => createCustomer(...args),
  updateCustomer: (...args: unknown[]) => updateCustomer(...args),
  listCollectionRisk: async () => [],
  listPriceLists: async () => [],
  verifyCustomerGstin: (...args: unknown[]) => verifyCustomerGstin(...args),
  verifyCustomersGstinBulk: (...args: unknown[]) => verifyCustomersGstinBulk(...args),
  lookupCustomerGstin: (...args: unknown[]) => lookupCustomerGstin(...args),
  deleteCustomer: (...args: unknown[]) => deleteCustomer(...args),
  setPosWalkInCustomer: (...args: unknown[]) => setPosWalkInCustomer(...args),
  exportCustomersCsv: (...args: unknown[]) => exportCustomersCsv(...args),
  getCustomer: (...args: unknown[]) => getCustomer(...args),
  getCustomersSummary: (...args: unknown[]) => getCustomersSummary(...args),
  getCustomersHealth: (...args: unknown[]) => getCustomersHealth(...args),
}));

function wrap(ui: ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

function apiError(status: number, details: Record<string, string[]> = {}, message = 'Validation failed') {
  return Object.assign(new Error(message), {
    isAxiosError: true,
    response: { status, data: { success: false, error: { code: 'invalid', message, details } } },
  });
}

const RAVI = { id: 1, name: 'Ravi Traders', status: 'ACTIVE', phone: '9999999999', version: 3 };

function listOf(...rows: Array<Record<string, unknown>>) {
  listCustomersPage.mockResolvedValue({ results: rows, count: rows.length, next: null, previous: null });
}

async function openDialog(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('button', { name: 'Add' }));
  return screen.findByRole('dialog');
}

beforeEach(() => {
  for (const fn of [
    listCustomersPage, createCustomer, updateCustomer, verifyCustomerGstin, verifyCustomersGstinBulk, lookupCustomerGstin,
    deleteCustomer, setPosWalkInCustomer, exportCustomersCsv, getCustomer, getCustomersSummary, getCustomersHealth,
  ]) fn.mockReset();
  getCustomersHealth.mockResolvedValue({ total: 0, checks: [] });
  currentUser = OWNER;
  writesBlocked = false;
  listOf(RAVI);
  getCustomersSummary.mockResolvedValue({
    totalCount: 3, activeCount: 2, blockedCount: 1, inactiveCount: 0, overCreditLimitCount: 1,
    totalOutstanding: '5000.00', totalUnallocatedAdvance: '200.00', netCreditExposure: '4800.00',
  });
  createCustomer.mockImplementation(async (payload: object) => ({ id: 2, ...payload }));
  updateCustomer.mockImplementation(async (id: number, payload: object) => ({ id, ...RAVI, ...payload }));
});

describe('CustomersPage toolbar', () => {
  it('labels the sort control "Sort by" and sends sort=recent', async () => {
    wrap(<CustomersPage />);
    expect(await screen.findByText('Ravi Traders')).toBeTruthy();
    await userEvent.click(screen.getByLabelText('Sort by'));
    await userEvent.click(await screen.findByRole('option', { name: /recently active/i }));
    expect(listCustomersPage).toHaveBeenCalledWith(expect.objectContaining({ sort: 'recent' }));
  });

  it('shows the portfolio strip and exports with the active filters', async () => {
    const user = userEvent.setup();
    exportCustomersCsv.mockResolvedValue(new Blob(['x']));
    wrap(<CustomersPage />);
    expect(await screen.findByText('Active customers')).toBeTruthy();
    expect(screen.getByText('2')).toBeTruthy();
    await user.click(screen.getByRole('button', { name: 'Export CSV' }));
    await waitFor(() => expect(exportCustomersCsv).toHaveBeenCalledWith(expect.objectContaining({ sort: 'name' })));
    expect(await screen.findByText('Customer list export started.')).toBeTruthy();
  });
});

describe('CustomersPage permissions', () => {
  it('hides write controls from a user without sales permission', async () => {
    currentUser = { ...OWNER, role: 'ACCOUNTANT', canCreateSales: false, canViewFinancialReports: true, canExport: true };
    wrap(<CustomersPage />);
    await screen.findByText('Ravi Traders');
    expect(screen.queryByRole('button', { name: 'Add' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Edit' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Block' })).toBeNull();
    expect(screen.getByRole('link', { name: 'Statement / Ledger' })).toBeTruthy();
  });

  it('hides the ledger link and summary from sales staff without report access', async () => {
    currentUser = { ...OWNER, role: 'SALES_STAFF', canCreateSales: true, canViewFinancialReports: false };
    wrap(<CustomersPage />);
    await screen.findByText('Ravi Traders');
    expect(screen.queryByRole('link', { name: 'Statement / Ledger' })).toBeNull();
    expect(screen.queryByText('Active customers')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Export CSV' })).toBeNull();
    expect(screen.getByRole('button', { name: 'Edit' })).toBeTruthy();
  });

  it('hides write controls while the subscription blocks writes', async () => {
    writesBlocked = true;
    wrap(<CustomersPage />);
    await screen.findByText('Ravi Traders');
    expect(screen.queryByRole('button', { name: 'Add' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Edit' })).toBeNull();
  });

  it('lets sales staff see but not change credit terms', async () => {
    currentUser = { ...OWNER, role: 'SALES_STAFF', canCreateSales: true, canViewFinancialReports: false };
    const user = userEvent.setup();
    wrap(<CustomersPage />);
    await screen.findByText('Ravi Traders');
    const dialog = await openDialog(user);
    expect((within(dialog).getByRole('textbox', { name: 'Credit limit' }) as HTMLInputElement).disabled).toBe(true);
    expect(within(dialog).getAllByText('Only an owner or manager can change credit terms.').length).toBeGreaterThan(0);
  });
});

describe('CustomersPage rows', () => {
  it('colours GSTIN status chips by the status the API stores', async () => {
    listOf(
      { id: 1, name: 'Valid Co', status: 'ACTIVE', gstin: G_KA, gstinVerificationStatus: 'VALID' },
      { id: 2, name: 'Cancelled Co', status: 'ACTIVE', gstin: G_MH, gstinVerificationStatus: 'CANCELLED' },
      { id: 3, name: 'Plain Co', status: 'ACTIVE', gstin: '07AABCU9603R1ZX', gstinVerificationStatus: 'UNVERIFIED' },
    );
    wrap(<CustomersPage />);
    await screen.findByText('Valid Co');
    const chip = (name: string) => {
      const row = screen.getByText(name).closest('tr')!;
      return within(row).getAllByText(/Verified|Cancelled|Unverified/).find((el) => el.className.includes('MuiChip'))!;
    };
    expect(chip('Valid Co').closest('.MuiChip-root')!.className).toContain('colorSuccess');
    expect(chip('Cancelled Co').closest('.MuiChip-root')!.className).toContain('colorError');
    expect(chip('Plain Co').closest('.MuiChip-root')!.className).toContain('colorWarning');
  });

  it('shows credit limit and net-of-advance captions', async () => {
    listOf({ id: 1, name: 'Limit Co', status: 'ACTIVE', outstanding: '900.00', creditLimit: '1000', creditExposure: '700.00' });
    wrap(<CustomersPage />);
    expect(await screen.findByText(/Limit ₹1,000/)).toBeTruthy();
    expect(screen.getByText(/Net of advances ₹700/)).toBeTruthy();
  });

  it('asks before blocking and sends the row version', async () => {
    const user = userEvent.setup();
    wrap(<CustomersPage />);
    await screen.findByText('Ravi Traders');
    await user.click(screen.getByRole('button', { name: 'Block' }));
    expect(updateCustomer).not.toHaveBeenCalled();
    const confirm = await screen.findByRole('dialog');
    await user.click(within(confirm).getByRole('button', { name: 'Block' }));
    await waitFor(() => expect(updateCustomer).toHaveBeenCalledWith(1, { status: 'BLOCKED', version: 3 }));
  });

  it('offers Activate (not Unblock) for an inactive customer', async () => {
    listOf({ id: 5, name: 'Old Co', status: 'INACTIVE', version: 1 });
    const user = userEvent.setup();
    wrap(<CustomersPage />);
    await screen.findByText('Old Co');
    expect(screen.queryByRole('button', { name: 'Unblock' })).toBeNull();
    await user.click(screen.getByRole('button', { name: 'Activate' }));
    await waitFor(() => expect(updateCustomer).toHaveBeenCalledWith(5, { status: 'ACTIVE', version: 1 }));
  });

  it('protects the POS walk-in customer', async () => {
    listOf({ id: 7, name: 'Walk-in', status: 'ACTIVE', isPosWalkIn: true });
    wrap(<CustomersPage />);
    await screen.findByText('Walk-in');
    expect(screen.getByText('POS walk-in')).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Block' })).toBeNull();
  });

  it('archives through a confirmation and reports an Inactive result', async () => {
    deleteCustomer.mockResolvedValue({ archived: true, detail: 'x' });
    const user = userEvent.setup();
    wrap(<CustomersPage />);
    await screen.findByText('Ravi Traders');
    await user.click(screen.getByRole('button', { name: 'More actions for Ravi Traders' }));
    await user.click(await screen.findByRole('menuitem', { name: 'Archive' }));
    const confirm = await screen.findByRole('dialog');
    await user.click(within(confirm).getByRole('button', { name: 'Archive' }));
    await waitFor(() => expect(deleteCustomer).toHaveBeenCalledWith(1));
    expect(await screen.findByText(/marked Inactive instead of deleted/)).toBeTruthy();
  });

  it('lets only an owner promote an eligible customer to POS walk-in', async () => {
    setPosWalkInCustomer.mockResolvedValue({ id: 1, name: 'Ravi Traders', status: 'ACTIVE', isPosWalkIn: true });
    const user = userEvent.setup();
    wrap(<CustomersPage />);
    await screen.findByText('Ravi Traders');
    await user.click(screen.getByRole('button', { name: 'More actions for Ravi Traders' }));
    await user.click(await screen.findByRole('menuitem', { name: 'Set as POS walk-in' }));
    await user.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Set as POS walk-in' }));
    await waitFor(() => expect(setPosWalkInCustomer).toHaveBeenCalledWith(1));
  });

  it('shows the verification notice when the provider could not verify', async () => {
    listOf({ id: 1, name: 'Ravi Traders', status: 'ACTIVE', gstin: G_KA, gstinVerificationStatus: 'UNVERIFIED' });
    verifyCustomerGstin.mockResolvedValue({
      id: 1, name: 'Ravi Traders', status: 'ACTIVE', verificationNotice: 'Live GSTIN verification is not configured.',
    });
    const user = userEvent.setup();
    wrap(<CustomersPage />);
    await screen.findByText('Ravi Traders');
    await user.click(screen.getByRole('button', { name: 'Verify' }));
    expect(await screen.findByText('Live GSTIN verification is not configured.')).toBeTruthy();
  });
});

describe('Customer form', () => {
  it('asks for both coordinates, validates range, and sends them together', async () => {
    const user = userEvent.setup();
    wrap(<CustomersPage />);
    await screen.findByText('Ravi Traders');
    const dialog = await openDialog(user);
    await user.type(within(dialog).getByRole('textbox', { name: /^Name/ }), 'Placed Shop');
    await user.click(within(dialog).getByRole('button', { name: 'Addresses and location' }));
    await user.type(within(dialog).getByRole('textbox', { name: 'Latitude' }), '12.97');
    expect(within(dialog).getByText('Enter both latitude and longitude, or leave both blank.')).toBeTruthy();
    expect((within(dialog).getByRole('button', { name: 'Save' }) as HTMLButtonElement).disabled).toBe(true);
    await user.type(within(dialog).getByRole('textbox', { name: 'Longitude' }), '977');
    expect(within(dialog).getByText(/Latitude must be between -90 and 90/)).toBeTruthy();
    await user.clear(within(dialog).getByRole('textbox', { name: 'Longitude' }));
    await user.type(within(dialog).getByRole('textbox', { name: 'Longitude' }), '77.59');
    await user.click(within(dialog).getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(createCustomer).toHaveBeenCalledWith(expect.objectContaining({
      name: 'Placed Shop', latitude: '12.97', longitude: '77.59',
    })));
  });

  it('sends null to clear saved coordinates and the row version', async () => {
    listOf({ ...RAVI, latitude: '12.970000', longitude: '77.590000' });
    const user = userEvent.setup();
    wrap(<CustomersPage />);
    await screen.findByText('Ravi Traders');
    await user.click(screen.getByRole('button', { name: 'Edit' }));
    const dialog = await screen.findByRole('dialog');
    await user.click(within(dialog).getByRole('button', { name: 'Addresses and location' }));
    await user.clear(within(dialog).getByRole('textbox', { name: 'Latitude' }));
    await user.clear(within(dialog).getByRole('textbox', { name: 'Longitude' }));
    await user.click(within(dialog).getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(updateCustomer).toHaveBeenCalledWith(1, expect.objectContaining({
      latitude: null, longitude: null, version: 3,
    })));
  });

  it('shows a server field error inside the open dialog and keeps what was typed', async () => {
    createCustomer.mockRejectedValue(apiError(400, { gstin: ["GSTIN is already registered to customer 'First Holder'."] }));
    const user = userEvent.setup();
    wrap(<CustomersPage />);
    await screen.findByText('Ravi Traders');
    const dialog = await openDialog(user);
    await user.type(within(dialog).getByRole('textbox', { name: /^Name/ }), 'Dup Co');
    await user.type(within(dialog).getByRole('textbox', { name: 'GSTIN' }), G_KA);
    await user.click(within(dialog).getByRole('button', { name: 'Save' }));
    expect(await within(dialog).findByText(/already registered to customer 'First Holder'/)).toBeTruthy();
    expect((within(dialog).getByRole('textbox', { name: /^Name/ }) as HTMLInputElement).value).toBe('Dup Co');
    // reopening starts clean
    await user.click(within(dialog).getByRole('button', { name: 'Cancel' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    const again = await openDialog(user);
    expect(within(again).queryByText(/First Holder/)).toBeNull();
  });

  it('fills state and PAN from a full GSTIN, and follows a changed prefix', async () => {
    const user = userEvent.setup();
    wrap(<CustomersPage />);
    await screen.findByText('Ravi Traders');
    const dialog = await openDialog(user);
    const gstin = within(dialog).getByRole('textbox', { name: 'GSTIN' });
    await user.type(gstin, G_KA);
    expect(within(dialog).getByRole('combobox', { name: /State/ }).textContent).toContain('Karnataka');
    expect((within(dialog).getByRole('textbox', { name: 'PAN' }) as HTMLInputElement).value).toBe('ABCDE1234F');
    await user.clear(gstin);
    await user.type(gstin, G_MH);
    expect(within(dialog).getByRole('combobox', { name: /State/ }).textContent).toContain('Maharashtra');
    expect((within(dialog).getByRole('textbox', { name: 'PAN' }) as HTMLInputElement).value).toBe('AABCU9603R');
  });

  it('flags a partial GSTIN as soon as it is typed', async () => {
    const user = userEvent.setup();
    wrap(<CustomersPage />);
    await screen.findByText('Ravi Traders');
    const dialog = await openDialog(user);
    await user.type(within(dialog).getByRole('textbox', { name: /^Name/ }), 'Partial Co');
    await user.type(within(dialog).getByRole('textbox', { name: 'GSTIN' }), '29ABC');
    expect(within(dialog).getByText('Enter a valid 15-character GSTIN')).toBeTruthy();
    expect((within(dialog).getByRole('button', { name: 'Save' }) as HTMLButtonElement).disabled).toBe(true);
  });

  it('verifies and autofills from the lookup, and warns about a duplicate', async () => {
    lookupCustomerGstin.mockResolvedValue({
      gstin: G_MH, status: 'UNVERIFIED', legalName: 'Acme Pvt Ltd', state: 'Maharashtra', pan: 'AABCU9603R',
      taxpayerType: 'REGULAR', provider: 'null', notice: 'Live GSTIN verification is not configured.',
      existingCustomer: { id: 8, name: 'Acme Old' },
    });
    const user = userEvent.setup();
    wrap(<CustomersPage />);
    await screen.findByText('Ravi Traders');
    const dialog = await openDialog(user);
    await user.type(within(dialog).getByRole('textbox', { name: 'GSTIN' }), G_MH);
    await user.click(within(dialog).getByRole('button', { name: 'Verify & autofill' }));
    expect(await within(dialog).findByText('Live GSTIN verification is not configured.')).toBeTruthy();
    expect(within(dialog).getByText('This GSTIN is already registered to Acme Old.')).toBeTruthy();
    await user.click(within(dialog).getByRole('button', { name: 'Use legal name: Acme Pvt Ltd' }));
    expect((within(dialog).getByRole('textbox', { name: /^Name/ }) as HTMLInputElement).value).toBe('Acme Pvt Ltd');
  });

  it('sends credit terms, tax class, addresses, notes and custom fields', async () => {
    const user = userEvent.setup();
    wrap(<CustomersPage />);
    await screen.findByText('Ravi Traders');
    const dialog = await openDialog(user);
    await user.type(within(dialog).getByRole('textbox', { name: /^Name/ }), 'Full Co');
    await user.type(within(dialog).getByRole('textbox', { name: 'Credit limit' }), '25000');
    await user.type(within(dialog).getByRole('textbox', { name: 'Credit days' }), '30');
    await user.click(within(dialog).getByRole('button', { name: 'Addresses and location' }));
    await user.click(within(dialog).getByRole('button', { name: 'Add delivery address' }));
    await user.type(within(dialog).getByRole('textbox', { name: 'Address' }), '12 Depot Road');
    await user.click(within(dialog).getByRole('button', { name: 'Other details' }));
    await user.type(await within(dialog).findByRole('textbox', { name: 'Drug licence' }), 'DL-77');
    await user.type(within(dialog).getByRole('textbox', { name: 'Notes' }), 'Pays on Fridays');
    await user.click(within(dialog).getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(createCustomer).toHaveBeenCalledWith(expect.objectContaining({
      name: 'Full Co', creditLimit: '25000', creditDays: 30, taxpayerType: 'UNREGISTERED',
      notes: 'Pays on Fridays', customFields: { dl: 'DL-77' },
      shippingAddresses: [expect.objectContaining({ address: '12 Depot Road' })],
    })));
  });

  it('offers to reload when someone else saved first, keeping the user edits', async () => {
    updateCustomer.mockRejectedValueOnce(apiError(409, {}, 'stale write'));
    getCustomer.mockResolvedValue({ ...RAVI, version: 4, notes: 'Changed elsewhere' });
    const user = userEvent.setup();
    wrap(<CustomersPage />);
    await screen.findByText('Ravi Traders');
    await user.click(screen.getByRole('button', { name: 'Edit' }));
    const dialog = await screen.findByRole('dialog');
    await user.click(within(dialog).getByRole('button', { name: 'Other details' }));
    await user.type(within(dialog).getByRole('textbox', { name: 'Notes' }), 'my note');
    await user.click(within(dialog).getByRole('button', { name: 'Save' }));
    expect(await within(dialog).findByText(/Someone else changed this customer/)).toBeTruthy();
    await user.click(within(dialog).getByRole('button', { name: 'Reload latest' }));
    await waitFor(() => expect(within(dialog).queryByText(/Someone else changed this customer/)).toBeNull());
    expect((within(dialog).getByRole('textbox', { name: 'Notes' }) as HTMLInputElement).value).toBe('my note');
    await user.click(within(dialog).getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(updateCustomer).toHaveBeenLastCalledWith(1, expect.objectContaining({ version: 4 })));
  });

  it('locks GSTIN and credit limit on the walk-in customer', async () => {
    listOf({ id: 7, name: 'Walk-in', status: 'ACTIVE', isPosWalkIn: true, version: 1 });
    const user = userEvent.setup();
    wrap(<CustomersPage />);
    await screen.findByText('Walk-in');
    await user.click(screen.getByRole('button', { name: 'Edit' }));
    const dialog = await screen.findByRole('dialog');
    expect((within(dialog).getByRole('textbox', { name: 'GSTIN' }) as HTMLInputElement).disabled).toBe(true);
    expect((within(dialog).getByRole('textbox', { name: 'Credit limit' }) as HTMLInputElement).disabled).toBe(true);
    expect(within(dialog).getByText(/This is the POS walk-in customer/)).toBeTruthy();
  });
});

describe('Customer form extras', () => {
  it('fills coordinates from the device location', async () => {
    const getCurrentPosition = vi.fn((ok: (p: unknown) => void) =>
      ok({ coords: { latitude: 12.971599, longitude: 77.594566 } }));
    Object.defineProperty(navigator, 'geolocation', { value: { getCurrentPosition }, configurable: true });
    const user = userEvent.setup();
    wrap(<CustomersPage />);
    await screen.findByText('Ravi Traders');
    const dialog = await openDialog(user);
    await user.click(within(dialog).getByRole('button', { name: 'Addresses and location' }));
    await user.click(within(dialog).getByRole('button', { name: 'Use current location' }));
    expect((within(dialog).getByRole('textbox', { name: 'Latitude' }) as HTMLInputElement).value).toBe('12.971599');
    expect((within(dialog).getByRole('textbox', { name: 'Longitude' }) as HTMLInputElement).value).toBe('77.594566');
  });

  it('says so when the location cannot be read', async () => {
    Object.defineProperty(navigator, 'geolocation', {
      value: { getCurrentPosition: (_ok: unknown, fail: () => void) => fail() },
      configurable: true,
    });
    const user = userEvent.setup();
    wrap(<CustomersPage />);
    await screen.findByText('Ravi Traders');
    const dialog = await openDialog(user);
    await user.click(within(dialog).getByRole('button', { name: 'Addresses and location' }));
    await user.click(within(dialog).getByRole('button', { name: 'Use current location' }));
    expect(await within(dialog).findByText(/Could not get your location/)).toBeTruthy();
  });

  it('treats a customer without a GSTIN as unregistered and a full GSTIN as regular', async () => {
    const user = userEvent.setup();
    wrap(<CustomersPage />);
    await screen.findByText('Ravi Traders');
    const dialog = await openDialog(user);
    const type = () => within(dialog).getByRole('combobox', { name: 'Taxpayer type' }).textContent;
    expect(type()).toContain('Unregistered');
    await user.type(within(dialog).getByRole('textbox', { name: 'GSTIN' }), G_KA);
    expect(type()).toContain('Regular');
  });
});

describe('CustomersPage archive role', () => {
  it('hides Archive from sales staff but not from a manager', async () => {
    currentUser = { ...OWNER, role: 'SALES_STAFF', canCreateSales: true };
    const staffView = wrap(<CustomersPage />);
    await screen.findByText('Ravi Traders');
    expect(screen.queryByRole('button', { name: /More actions/ })).toBeNull();
    staffView.unmount();
    currentUser = { ...OWNER, role: 'MANAGER', canCreateSales: true };
    wrap(<CustomersPage />);
    await screen.findByText('Ravi Traders');
    expect(screen.getByRole('button', { name: /More actions/ })).toBeTruthy();
  });
});

describe('CustomersPage review fixes', () => {
  it('lets sales staff block but not unblock or activate', async () => {
    currentUser = { ...OWNER, role: 'SALES_STAFF', canCreateSales: true };
    listOf(
      { id: 1, name: 'Live Co', status: 'ACTIVE', version: 1 },
      { id: 2, name: 'Held Co', status: 'BLOCKED', version: 1 },
      { id: 3, name: 'Old Co', status: 'INACTIVE', version: 1 },
    );
    wrap(<CustomersPage />);
    await screen.findByText('Live Co');
    expect(screen.getAllByRole('button', { name: 'Block' })).toHaveLength(1);
    expect(screen.queryByRole('button', { name: 'Unblock' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Activate' })).toBeNull();
  });

  it('lets a manager unblock', async () => {
    currentUser = { ...OWNER, role: 'MANAGER', canCreateSales: true };
    listOf({ id: 2, name: 'Held Co', status: 'BLOCKED', version: 1 });
    const user = userEvent.setup();
    wrap(<CustomersPage />);
    await screen.findByText('Held Co');
    await user.click(screen.getByRole('button', { name: 'Unblock' }));
    await waitFor(() => expect(updateCustomer).toHaveBeenCalledWith(2, { status: 'ACTIVE', version: 1 }));
  });

  it('reaches Verify GSTIN from the row menu (the way to it on a phone)', async () => {
    currentUser = { ...OWNER, role: 'SALES_STAFF', canCreateSales: true };
    listOf({ id: 1, name: 'Ravi Traders', status: 'ACTIVE', gstin: G_KA, gstinVerificationStatus: 'UNVERIFIED' });
    verifyCustomerGstin.mockResolvedValue({ id: 1, name: 'Ravi Traders', status: 'ACTIVE' });
    const user = userEvent.setup();
    wrap(<CustomersPage />);
    await screen.findByText('Ravi Traders');
    await user.click(screen.getByRole('button', { name: 'More actions for Ravi Traders' }));
    await user.click(await screen.findByRole('menuitem', { name: 'Verify GSTIN' }));
    await waitFor(() => expect(verifyCustomerGstin).toHaveBeenCalledWith(1));
  });

  it('shows an error for a server field the form does not have', async () => {
    createCustomer.mockRejectedValue(apiError(400, { name: ['Name is taken.'], priceList: ['Bad list.'], mystery: ['Odd.'] }));
    const user = userEvent.setup();
    wrap(<CustomersPage />);
    await screen.findByText('Ravi Traders');
    const dialog = await openDialog(user);
    await user.type(within(dialog).getByRole('textbox', { name: /^Name/ }), 'Odd Co');
    await user.click(within(dialog).getByRole('button', { name: 'Save' }));
    // Unknown server fields are shown with a readable label (fieldLabel in api/client.ts).
    expect(await within(dialog).findByText(/Mystery: Odd\./)).toBeTruthy();
    expect(within(dialog).getByText('Name is taken.')).toBeTruthy();
  });
});

describe('CustomersPage remaining items', () => {
  it('verifies several selected customers at once and reports the outcome', async () => {
    listOf(
      { id: 1, name: 'One Co', status: 'ACTIVE', gstin: G_KA, version: 1 },
      { id: 2, name: 'Two Co', status: 'ACTIVE', gstin: G_MH, version: 1 },
      { id: 3, name: 'No Gstin Co', status: 'ACTIVE', version: 1 },
    );
    verifyCustomersGstinBulk.mockResolvedValue({
      results: [
        { id: 1, status: 'UNVERIFIED', notice: '', error: '' },
        { id: 2, status: '', notice: '', error: 'Customer has no GSTIN.' },
      ],
    });
    const user = userEvent.setup();
    wrap(<CustomersPage />);
    await screen.findByText('One Co');
    expect(screen.queryByRole('checkbox', { name: 'Select No Gstin Co to verify' })).toBeNull();
    await user.click(screen.getByRole('checkbox', { name: 'Select all customers with a GSTIN' }));
    await user.click(screen.getByRole('button', { name: 'Verify selected (2)' }));
    await waitFor(() => expect(verifyCustomersGstinBulk).toHaveBeenCalledWith([1, 2]));
    expect(await screen.findByText(/Checked 1, 1 failed: Customer has no GSTIN\./)).toBeTruthy();
  });

  it('refuses a selection larger than the batch limit', async () => {
    listOf(...Array.from({ length: 11 }, (_v, i) => ({ id: i + 1, name: `Co ${i + 1}`, status: 'ACTIVE', gstin: G_KA, version: 1 })));
    const user = userEvent.setup();
    wrap(<CustomersPage />);
    await screen.findByText('Co 1');
    await user.click(screen.getByRole('checkbox', { name: 'Select all customers with a GSTIN' }));
    const button = screen.getByRole('button', { name: 'Select at most 10 to verify' }) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
  });

  it('offers a way to the archived customers', async () => {
    getCustomersSummary.mockResolvedValue({
      totalCount: 5, activeCount: 3, blockedCount: 0, inactiveCount: 2, overCreditLimitCount: 0,
      totalOutstanding: '0', totalUnallocatedAdvance: '0', netCreditExposure: '0',
    });
    const user = userEvent.setup();
    wrap(<CustomersPage />);
    await screen.findByText('Ravi Traders');
    await user.click(await screen.findByRole('button', { name: '2 archived' }));
    await waitFor(() => expect(listCustomersPage).toHaveBeenCalledWith(expect.objectContaining({ status: 'INACTIVE' })));
  });

  it('shows the conflict message when blocking races another editor', async () => {
    updateCustomer.mockRejectedValueOnce(apiError(409, {}, 'This customer was changed by someone else. Reload it and try again.'));
    const user = userEvent.setup();
    wrap(<CustomersPage />);
    await screen.findByText('Ravi Traders');
    await user.click(screen.getByRole('button', { name: 'Block' }));
    await user.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Block' }));
    expect(await screen.findByText(/changed by someone else/)).toBeTruthy();
  });
});

describe('CustomersPage health banner', () => {
  it('tells an owner which customer records need a look', async () => {
    getCustomersHealth.mockResolvedValue({
      total: 3,
      checks: [
        { check: 'state_mismatch', label: 'x', count: 2 },
        { check: 'duplicate_gstin', label: 'y', count: 1 },
      ],
    });
    wrap(<CustomersPage />);
    expect(
      await screen.findByText(/3 customer records need a look: 2 state that disagrees with the GSTIN; 1 duplicate GSTIN\./),
    ).toBeTruthy();
  });

  it('does not ask sales staff or show them the banner', async () => {
    currentUser = { ...OWNER, role: 'SALES_STAFF', canCreateSales: true };
    wrap(<CustomersPage />);
    await screen.findByText('Ravi Traders');
    expect(getCustomersHealth).not.toHaveBeenCalled();
    expect(screen.queryByText(/need a look/)).toBeNull();
  });
});

describe('CustomersPage accessibility', () => {
  // jsdom cannot compute colour contrast or layout, so those rules are left to the browser pass.
  async function violations() {
    const results = await axe.run(document.body, {
      rules: { 'color-contrast': { enabled: false }, region: { enabled: false } },
    });
    return results.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(' ')).join(' | ')}`);
  }

  it('has no violations on the list', async () => {
    wrap(<CustomersPage />);
    expect(await screen.findByText('Ravi Traders')).toBeTruthy();
    expect(await screen.findByText('Active customers')).toBeTruthy();
    expect(await violations()).toEqual([]);
  });

  it('has no violations in the form dialog, and focus returns to the Edit button on close', async () => {
    const user = userEvent.setup();
    wrap(<CustomersPage />);
    await screen.findByText('Ravi Traders');
    const edit = screen.getByRole('button', { name: 'Edit' });
    await user.click(edit);
    const dialog = await screen.findByRole('dialog');
    expect(await violations()).toEqual([]);
    await user.click(within(dialog).getByRole('button', { name: 'Cancel' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    await waitFor(() => expect(document.activeElement).toBe(edit));
  });

  it('has no violations in the block confirmation', async () => {
    const user = userEvent.setup();
    wrap(<CustomersPage />);
    await screen.findByText('Ravi Traders');
    await user.click(screen.getByRole('button', { name: 'Block' }));
    await screen.findByRole('dialog');
    expect(await violations()).toEqual([]);
  });
});
