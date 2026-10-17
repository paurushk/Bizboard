import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactElement } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { FixedAssetsPage } from '@/pages/phase/FixedAssetsPage';
import * as resources from '@/api/resources';

const state = vi.hoisted(() => ({
  mismatch: false,
  failing: false,
  listError: null as unknown,
}));

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ user: { id: 1, role: 'OWNER', canPostJournals: true } }),
}));
vi.mock('@/hooks/useSubscriptionGate', () => ({
  useSubscriptionGate: () => ({ writesBlocked: false }),
}));
vi.mock('@/components/billing', () => ({ todayIso: () => '2026-10-16' }));
vi.mock('@/api/resources', () => ({
  listFixedAssets: async () => {
    if (state.listError) throw state.listError;
    return [
      {
        id: 5, name: 'Laptop', acquisitionCost: '120000.00', depreciatedAmount: '40000.00', netBookValue: '80000.00',
        acquisitionDate: '2026-01-15', usefulLifeMonths: 36, status: 'ACTIVE', method: 'SLM', lastDepreciationMonth: '2026-09',
        depreciationErrors: state.failing ? [{ month: '2026-08', reason: 'period closed' }] : [], catchupMonths: [],
      },
    ];
  },
  getFixedAssetSummary: async () => ({
    count: 1, totalCost: '120000.00', accumulated: '40000.00', netBookValue: '80000.00', thisMonthCharge: '3333.33', errors: 0,
    lastCompletedMonth: '2026-09',
    registerVsGl: {
      registerCost: '120000.00', glCost: state.mismatch ? '0.00' : '120000.00', costDifference: state.mismatch ? '120000.00' : '0.00',
      registerAccumulated: '40000.00', glAccumulated: '40000.00', accumulatedDifference: '0.00',
    },
  }),
  getFixedAssetSchedule: async () => ({
    asset: 5, disposal: null,
    rows: [
      { month: '2026-01', amount: '1500.00', status: 'posted', journalId: 1, number: 'JV-1', accumulated: '1500.00' },
      { month: '2026-10', amount: '3333.33', status: 'projected', journalId: null, number: '', accumulated: '4833.33' },
    ],
  }),
  listFixedAssetPresets: async () => ({
    note: 'Check these with your CA.',
    results: [{ key: 'computers', name: 'Computers and laptops', usefulLifeMonths: 36, method: 'SLM', wdvAnnualRate: '40.00' }],
  }),
  runFixedAssetDepreciation: vi.fn(async (p: { dryRun?: boolean }) => ({
    through: '2026-09', dryRun: Boolean(p.dryRun), posted: p.dryRun ? 0 : 2, total: '6666.66',
    assets: [{ asset: 5, name: 'Laptop', errors: [], months: [{ month: '2026-08', amount: '3333.33', status: p.dryRun ? 'would_post' : 'posted' }] }],
  })),
  draftAssetRegisterFix: vi.fn(async () => ({ journalId: 3, number: 'JV-3' })),
  listBankAccounts: async () => [{ id: 11, name: 'HDFC Current' }],
  listSuppliers: async () => [{ id: 21, name: 'Dell' }],
  listAccounts: async () => [],
  disposeFixedAsset: vi.fn(async () => ({})),
  createFixedAsset: vi.fn(async () => ({})),
  updateFixedAsset: vi.fn(async () => ({})),
}));

function wrap(ui: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  state.mismatch = false;
  state.failing = false;
  state.listError = null;
  vi.clearAllMocks();
});

describe('FixedAssetsPage disposal (ACS-12)', () => {
  it('asks for date and proceeds, previews the gain, and sends them to the server', async () => {
    const nativePrompt = vi.spyOn(window, 'prompt');
    wrap(<FixedAssetsPage />);
    await userEvent.click(await screen.findByRole('button', { name: 'Dispose' }));
    const dialog = await screen.findByRole('dialog');
    const confirm = within(dialog).getByRole('button', { name: 'Dispose asset' });
    expect(confirm).toBeDisabled(); // name not typed yet

    await userEvent.type(within(dialog).getByLabelText('Sale proceeds'), '90000');
    // NBV = 120,000 - 40,000 = 80,000 -> gain of 10,000
    expect(dialog.textContent).toMatch(/Net book value/);
    expect(dialog.textContent).toMatch(/Gain on disposal/);
    expect(dialog.textContent).toMatch(/10,000/);

    await userEvent.click(within(dialog).getByLabelText('Received in'));
    await userEvent.click(await screen.findByRole('option', { name: 'HDFC Current' }));
    await userEvent.type(within(dialog).getByLabelText('Type the asset name to confirm'), 'Laptop');
    expect(confirm).toBeEnabled();
    await userEvent.click(confirm);

    expect(resources.disposeFixedAsset).toHaveBeenCalledWith(5, {
      confirm: true, proceeds: 90000, disposalDate: '2026-10-16', chargePartMonth: true, bankAccount: 11,
    });
    expect(nativePrompt).not.toHaveBeenCalled();
    nativePrompt.mockRestore();
  });

  it('shows a loss and refuses a disposal date before the purchase date', async () => {
    wrap(<FixedAssetsPage />);
    await userEvent.click(await screen.findByRole('button', { name: 'Dispose' }));
    const dialog = await screen.findByRole('dialog');
    await userEvent.type(within(dialog).getByLabelText('Sale proceeds'), '50000');
    expect(dialog.textContent).toMatch(/Loss on disposal/);

    const date = within(dialog).getByLabelText('Disposal date');
    await userEvent.clear(date);
    await userEvent.type(date, '2025-12-31');
    expect(dialog.textContent).toMatch(/cannot be before the purchase date/);
    await userEvent.type(within(dialog).getByLabelText('Type the asset name to confirm'), 'Laptop');
    expect(within(dialog).getByRole('button', { name: 'Dispose asset' })).toBeDisabled();
  });

  it('lets the owner leave out the part-month charge', async () => {
    wrap(<FixedAssetsPage />);
    await userEvent.click(await screen.findByRole('button', { name: 'Dispose' }));
    const dialog = await screen.findByRole('dialog');
    await userEvent.click(within(dialog).getByLabelText('Charge depreciation up to the sale date'));
    await userEvent.type(within(dialog).getByLabelText('Type the asset name to confirm'), 'Laptop');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Dispose asset' }));
    expect(resources.disposeFixedAsset).toHaveBeenCalledWith(5, { confirm: true, proceeds: 0, disposalDate: '2026-10-16' });
  });
});

describe('FixedAssetsPage register (ACS-52..55)', () => {
  it('shows summary cards and the net book value column', async () => {
    wrap(<FixedAssetsPage />);
    const cards = await screen.findByTestId('asset-summary');
    expect(within(cards).getByText('Net book value')).toBeTruthy();
    expect(within(cards).getByText(/3,333/)).toBeTruthy();
    expect(screen.getByText('2026-09')).toBeTruthy();
  });

  it('warns when the register and the ledger disagree and drafts the correcting journal', async () => {
    state.mismatch = true;
    wrap(<FixedAssetsPage />);
    expect(await screen.findByText(/register and the ledger differ/)).toBeTruthy();
    await userEvent.click(screen.getByRole('button', { name: 'Draft correcting journal' }));
    await waitFor(() => expect(resources.draftAssetRegisterFix).toHaveBeenCalled());
    expect(await screen.findByText(/Draft journal JV-3 made/)).toBeTruthy();
  });

  it('lists depreciation errors against the asset and month', async () => {
    state.failing = true;
    wrap(<FixedAssetsPage />);
    expect(await screen.findByText(/Depreciation could not be posted/)).toBeTruthy();
    expect(screen.getByText(/2026-08 period closed/)).toBeTruthy();
  });

  it('opens the schedule drawer with posted and projected months', async () => {
    wrap(<FixedAssetsPage />);
    await userEvent.click(await screen.findByRole('button', { name: 'Details Laptop' }));
    expect(await screen.findByText('JV-1')).toBeTruthy();
    expect(screen.getByText('Projected')).toBeTruthy();
  });

  it('previews depreciation before posting it', async () => {
    wrap(<FixedAssetsPage />);
    await userEvent.click(await screen.findByRole('button', { name: 'Run depreciation' }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByRole('button', { name: 'Post these' })).toBeDisabled();
    await userEvent.click(within(dialog).getByRole('button', { name: 'Preview' }));
    expect(await within(dialog).findByText(/would post/)).toBeTruthy();
    await userEvent.click(within(dialog).getByRole('button', { name: 'Post these' }));
    await waitFor(() => expect(resources.runFixedAssetDepreciation).toHaveBeenLastCalledWith({ month: '2026-09', dryRun: false }));
  });

  it('registers an asset paid from the bank with the preset values', async () => {
    wrap(<FixedAssetsPage />);
    await userEvent.click(await screen.findByRole('button', { name: 'Add asset' }));
    const dialog = await screen.findByRole('dialog');
    await userEvent.type(within(dialog).getByLabelText(/^Name/), 'New laptop');
    await userEvent.type(within(dialog).getByLabelText('Acquisition cost'), '50000');
    await userEvent.click(within(dialog).getByLabelText('Start from a type of asset'));
    await userEvent.click(await screen.findByRole('option', { name: 'Computers and laptops' }));
    await userEvent.click(within(dialog).getByLabelText('How was it paid for?'));
    await userEvent.click(await screen.findByRole('option', { name: 'Paid from a bank account' }));
    const save = within(dialog).getByRole('button', { name: 'Save' });
    expect(save).toBeDisabled(); // bank not chosen yet
    await userEvent.click(within(dialog).getByLabelText(/Bank account/));
    await userEvent.click(await screen.findByRole('option', { name: 'HDFC Current' }));
    await userEvent.click(save);
    await waitFor(() => expect(resources.createFixedAsset).toHaveBeenCalled());
    const body = vi.mocked(resources.createFixedAsset).mock.calls[0][0] as Record<string, unknown>;
    expect(body).toMatchObject({ funding: 'BANK', fundingBankAccount: 11, usefulLifeMonths: 36, method: 'SLM', category: 'computers', acquisitionCost: 50000 });
  });

  it('says plainly when the module is switched off', async () => {
    state.listError = Object.assign(new Error('nope'), { isAxiosError: true, response: { status: 404, data: {} } });
    wrap(<FixedAssetsPage />);
    expect(await screen.findByText(/switched off for this account/)).toBeTruthy();
  });
});
