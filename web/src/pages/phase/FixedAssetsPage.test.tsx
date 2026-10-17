import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactElement } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { FixedAssetsPage } from '@/pages/phase/FixedAssetsPage';
import * as resources from '@/api/resources';

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ user: { id: 1, role: 'OWNER', canPostJournals: true } }),
}));
vi.mock('@/hooks/useSubscriptionGate', () => ({
  useSubscriptionGate: () => ({ writesBlocked: false }),
}));
vi.mock('@/components/billing', () => ({ todayIso: () => '2026-10-16' }));
vi.mock('@/api/resources', () => ({
  listFixedAssets: async () => [
    {
      id: 5, name: 'Laptop', acquisitionCost: '120000.00', depreciatedAmount: '40000.00',
      acquisitionDate: '2026-01-15', usefulLifeMonths: 36, status: 'ACTIVE',
    },
  ],
  listBankAccounts: async () => [{ id: 11, name: 'HDFC Current' }],
  disposeFixedAsset: vi.fn(async () => ({})),
  createFixedAsset: vi.fn(),
  updateFixedAsset: vi.fn(),
}));

function wrap(ui: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

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
      confirm: true, proceeds: 90000, disposalDate: '2026-10-16', bankAccount: 11,
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
});
