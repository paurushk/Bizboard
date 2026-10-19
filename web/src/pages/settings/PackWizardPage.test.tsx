import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { t } from '@/i18n';
import { PackWizardPage } from '@/pages/settings/PackWizardPage';

const api = vi.hoisted(() => ({
  getPackWizard: vi.fn(),
  proposePack: vi.fn(),
  confirmPack: vi.fn(),
  setNavScope: vi.fn(),
}));
vi.mock('@/api/osPlan', () => api);
vi.mock('@/config/featureFlags', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/config/featureFlags')>();
  return { ...actual, fetchFeatureFlags: vi.fn(async () => ({})), isRuntimeFlagEnabled: () => false };
});

const WIZARD = {
  answers: { what_you_sell: 'rice', how_you_sell: 'counter', deliver: 'no', gst_registered: 'yes' },
  proposedPack: 'retail',
  appliedPack: '',
  packs: { retail: ['ENABLE_POS', 'ENABLE_GSTR'], trade: ['ENABLE_CRM'] },
  heldPacks: [],
  confirmedAt: null,
};
const PREVIEW = {
  pack: 'retail',
  wouldEnable: ['ENABLE_POS'],
  alreadyOn: ['ENABLE_GSTR'],
  keptAsSet: ['ENABLE_REPLENISHMENT'],
  unavailable: ['ENABLE_CRM'],
};

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <PackWizardPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('PackWizardPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getPackWizard.mockResolvedValue(WIZARD);
    api.proposePack.mockResolvedValue({ proposedPack: 'retail', applied: false, preview: PREVIEW });
    api.confirmPack.mockResolvedValue({ proposedPack: 'retail', appliedPack: 'retail', applied: true, skippedFlags: ['ENABLE_CRM'] });
  });

  it('cannot apply before the pack has been previewed', async () => {
    renderPage();
    const apply = (await screen.findByRole('button', { name: t('osPlan.applyPack') })) as HTMLButtonElement;
    expect(apply.disabled).toBe(true);
    expect(screen.getByText(t('packPreview.seeFirst'))).toBeTruthy();
  });

  it('shows what the pack will do in four groups, and that it only turns things on', async () => {
    renderPage();
    await userEvent.click(await screen.findByRole('button', { name: t('osPlan.seePack') }));
    expect(await screen.findByText(t('packPreview.onlyOn'))).toBeTruthy();
    expect(screen.getByText('ENABLE_POS')).toBeTruthy();
    expect(screen.getByText(t('packPreview.wouldEnable') + ':')).toBeTruthy();
    expect(screen.getByText(t('packPreview.alreadyOn') + ':')).toBeTruthy();
    expect(screen.getByText(t('packPreview.keptAsSet') + ':')).toBeTruthy();
    expect(screen.getByText(t('packPreview.unavailable') + ':')).toBeTruthy();
    expect((screen.getByRole('button', { name: t('osPlan.applyPack') }) as HTMLButtonElement).disabled).toBe(false);
  });

  it('says so when there is nothing to switch on', async () => {
    api.proposePack.mockResolvedValue({ proposedPack: 'retail', applied: false, preview: { ...PREVIEW, wouldEnable: [] } });
    renderPage();
    await userEvent.click(await screen.findByRole('button', { name: t('osPlan.seePack') }));
    expect(await screen.findByText(t('packPreview.nothing'))).toBeTruthy();
  });

  it('asks to preview again once an answer has changed', async () => {
    renderPage();
    await userEvent.click(await screen.findByRole('button', { name: t('osPlan.seePack') }));
    await screen.findByText(t('packPreview.onlyOn'));
    await userEvent.type(screen.getByLabelText(t('osPlan.whatYouSell')), ' and dal');
    expect(await screen.findByText(t('packPreview.changed'))).toBeTruthy();
    expect(screen.queryByText(t('packPreview.onlyOn'))).toBeNull();
    expect((screen.getByRole('button', { name: t('osPlan.applyPack') }) as HTMLButtonElement).disabled).toBe(true);
  });

  it('applies the previewed pack and reports what was skipped', async () => {
    renderPage();
    await userEvent.click(await screen.findByRole('button', { name: t('osPlan.seePack') }));
    await screen.findByText(t('packPreview.onlyOn'));
    await userEvent.click(screen.getByRole('button', { name: t('osPlan.applyPack') }));
    await waitFor(() => expect(api.confirmPack).toHaveBeenCalledTimes(1));
    expect(await screen.findByText(t('osPlan.packSaved'))).toBeTruthy();
    expect(screen.getByText(t('osPlan.packSkipped', { names: 'ENABLE_CRM' }))).toBeTruthy();
  });

  it('shows the server reason when applying is refused', async () => {
    api.confirmPack.mockRejectedValueOnce(new Error('Unknown pack.'));
    renderPage();
    await userEvent.click(await screen.findByRole('button', { name: t('osPlan.seePack') }));
    await screen.findByText(t('packPreview.onlyOn'));
    await userEvent.click(screen.getByRole('button', { name: t('osPlan.applyPack') }));
    expect(await screen.findByText(/Unknown pack/)).toBeTruthy();
  });

  it('shows an error with Retry when the wizard cannot load', async () => {
    api.getPackWizard.mockRejectedValue(new Error('down'));
    renderPage();
    expect(await screen.findByRole('button', { name: /retry|try again/i })).toBeTruthy();
  });
});
