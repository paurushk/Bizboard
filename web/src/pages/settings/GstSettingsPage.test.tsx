import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { t } from '@/i18n';
import { GstSettingsPage } from '@/pages/settings/GstSettingsPage';

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({ user: { id: 1, role: 'OWNER', companyId: 9, company: {} } }),
}));
vi.mock('@/pages/settings/BranchGstinsPanel', () => ({ BranchGstinsPanel: () => <div>branch-panel</div> }));
vi.mock('@/pages/help/HelpHint', () => ({ HelpHint: ({ children }: { children: React.ReactNode }) => <>{children}</> }));

const api = vi.hoisted(() => ({
  getCompany: vi.fn(),
  updateCompany: vi.fn(),
  verifyCompanyGstin: vi.fn(),
  verifyCompanyPan: vi.fn(),
  verifyCompanyUdyam: vi.fn(),
  previewSettingsChange: vi.fn(),
}));
vi.mock('@/api/resources', () => api);

const COMPANY = {
  gstin: '07AAACB2894G1ZP',
  pan: '',
  udyam: '',
  state: 'Delhi',
  registrationType: 'REGULAR',
  negativeStockPolicy: 'BLOCK',
  valuationBusinessDateOrder: false,
  recomputeTaxOnComplete: false,
  assumeLocalStateForBlankParty: true,
  einvoiceEnabled: false,
  ewayEnabled: false,
  ewayThresholdAmount: '50000',
  aatoTurnover: '',
  gspProvider: '',
  gspCredentialsConfigured: false,
};

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <GstSettingsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const section = (name: string) => screen.getByRole('region', { name });
const saveIn = (name: string) => within(section(name)).getByRole('button', { name: t('common.save') });

describe('GstSettingsPage sections (SET-16)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getCompany.mockResolvedValue(COMPANY);
    api.updateCompany.mockResolvedValue(COMPANY);
    api.previewSettingsChange.mockResolvedValue([]);
  });

  it('shows three saveable sections plus the branch GSTINs, each with its own Save', async () => {
    renderPage();
    for (const key of ['registrationTitle', 'stockTitle', 'einvoiceTitle']) {
      expect(await screen.findByRole('region', { name: t(`gstPage.${key}`) })).toBeTruthy();
    }
        expect(screen.getByText('branch-panel')).toBeTruthy();
    expect(screen.getAllByRole('button', { name: t('common.save') })).toHaveLength(3);
  });

  it('shows e-invoice, e-way and portal state as status only, with no switch to flip', async () => {
    renderPage();
    const sec = await screen.findByRole('region', { name: t('gstPage.einvoiceTitle') });
    expect(within(sec).queryByRole('checkbox')).toBeNull();
    expect(within(sec).getByText(t('gstPage.controlledByBizboard'))).toBeTruthy();
    expect(within(sec).getAllByText(t('gstPage.statusOff')).length).toBeGreaterThan(0);
  });

  it('saves the e-way limit on its own and sends nothing else', async () => {
    renderPage();
    const field = await screen.findByLabelText(t('gstSettings.ewayThreshold'));
    await userEvent.clear(field);
    await userEvent.type(field, '75000');
    await userEvent.click(saveIn(t('gstPage.einvoiceTitle')));
    await waitFor(() => expect(api.updateCompany).toHaveBeenCalledTimes(1));
    expect(api.updateCompany.mock.calls[0][0]).toEqual({ eway_threshold_amount: '75000' });
  });

  it('refuses an e-way limit that is not a number', async () => {
    renderPage();
    const field = await screen.findByLabelText(t('gstSettings.ewayThreshold'));
    await userEvent.clear(field);
    await userEvent.type(field, 'lots');
    await userEvent.click(saveIn(t('gstPage.einvoiceTitle')));
    expect(await screen.findByText(t('gstPage.thresholdInvalid'))).toBeTruthy();
    expect(api.updateCompany).not.toHaveBeenCalled();
  });

  it('keeps a half-edited GSTIN out of an e-invoice save, and still lets that save through', async () => {
    renderPage();
    const gstin = await screen.findByLabelText(t('gstSettings.primaryGstin'));
    await userEvent.type(gstin, 'X');
    const limit = within(section(t('gstPage.einvoiceTitle'))).getByLabelText(t('gstSettings.ewayThreshold'));
    await userEvent.type(limit, '0');
    await userEvent.click(saveIn(t('gstPage.einvoiceTitle')));
    await waitFor(() => expect(api.updateCompany).toHaveBeenCalledTimes(1));
    expect(api.updateCompany.mock.calls[0][0]).not.toHaveProperty('gstin');
  });

  it('refuses an invalid GSTIN with a reason and does not send it', async () => {
    renderPage();
    const gstin = await screen.findByLabelText(t('gstSettings.primaryGstin'));
    await userEvent.clear(gstin);
    await userEvent.type(gstin, '123');
    await userEvent.click(saveIn(t('gstPage.registrationTitle')));
    expect(await screen.findByText(t('gstPage.gstinInvalid'))).toBeTruthy();
    expect(api.updateCompany).not.toHaveBeenCalled();
  });

  it('wants the confirmation tick before a changed GSTIN is saved', async () => {
    renderPage();
    const gstin = await screen.findByLabelText(t('gstSettings.primaryGstin'));
    await userEvent.clear(gstin);
    await userEvent.type(gstin, '29ABCDE1234F1ZW');
    await userEvent.click(saveIn(t('gstPage.registrationTitle')));
    expect(await screen.findAllByText(t('cog.gstConfirm'))).not.toHaveLength(0);
    expect(api.updateCompany).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole('checkbox', { name: t('cog.gstConfirm') }));
    await userEvent.click(saveIn(t('gstPage.registrationTitle')));
    await waitFor(() => expect(api.updateCompany).toHaveBeenCalledTimes(1));
    expect(api.updateCompany.mock.calls[0][0]).toMatchObject({ gstin: '29ABCDE1234F1ZW', confirm_tax_profile: true });
  });

  it('previews a registration type change with the drafts it touches, and saves only after yes', async () => {
    api.previewSettingsChange.mockResolvedValue([{ key: 'drafts_affected', params: { count: 3 } }]);
    window.confirm = vi.fn(() => true);
    renderPage();
    await screen.findByRole('region', { name: t('gstPage.registrationTitle') });
    await userEvent.click(within(section(t('gstPage.registrationTitle'))).getByLabelText(t('gstSettings.registrationType')));
    await userEvent.click(await screen.findByRole('option', { name: t('gstSettings.composition') }));
    await userEvent.click(saveIn(t('gstPage.registrationTitle')));
    await waitFor(() => expect(api.updateCompany).toHaveBeenCalledTimes(1));
    expect(api.previewSettingsChange).toHaveBeenCalledWith('gst_registration', expect.objectContaining({ registration_type: 'COMPOSITION' }));
    expect(String((window.confirm as ReturnType<typeof vi.fn>).mock.calls[0][0])).toContain(t('settingsPreview.drafts_affected', { count: '3' }));
  });

  it('asks before changing the negative stock policy and does not save when declined', async () => {
    window.confirm = vi.fn(() => false);
    renderPage();
    await screen.findByRole('region', { name: t('gstPage.stockTitle') });
    await userEvent.click(within(section(t('gstPage.stockTitle'))).getByLabelText(t('gstSettings.stockPolicy')));
    await userEvent.click(await screen.findByRole('option', { name: t('gstSettings.allowWarn') }));
    await userEvent.click(saveIn(t('gstPage.stockTitle')));
    expect(window.confirm).toHaveBeenCalled();
    expect(api.updateCompany).not.toHaveBeenCalled();
  });

  it('shows an error with Retry rather than a blank form when the company cannot load', async () => {
    api.getCompany.mockRejectedValue(new Error('down'));
    renderPage();
    expect(await screen.findByRole('button', { name: /retry|try again/i })).toBeTruthy();
    expect(screen.queryByLabelText(t('gstSettings.primaryGstin'))).toBeNull();
  });
});
