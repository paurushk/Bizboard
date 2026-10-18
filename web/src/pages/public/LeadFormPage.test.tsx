import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { submitPublicLead } from '@/api/osPlan';
import { LeadFormPage } from '@/pages/public/LeadFormPage';

vi.mock('@/api/osPlan', () => ({
  submitPublicLead: vi.fn().mockResolvedValue(undefined),
  getPublicLeadFormMeta: vi.fn().mockResolvedValue({
    companyName: 'Alpha Traders',
    consentText: 'By sending this form you agree that Alpha Traders may contact you about your enquiry.',
  }),
}));

function renderForm(entry = '/lead-form/preview') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[entry]}>
        <Routes>
          <Route path="/lead-form/:token" element={<LeadFormPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('LeadFormPage', () => {
  beforeEach(() => vi.mocked(submitPublicLead).mockClear());

  it('shows the company name and consent line and has no campaign id field', async () => {
    renderForm();
    expect(await screen.findByText('Your message goes to Alpha Traders.')).toBeInTheDocument();
    expect(screen.getByText(/may contact you about your enquiry/)).toBeInTheDocument();
    expect(screen.queryByRole('textbox', { name: 'Campaign id' })).not.toBeInTheDocument();
  });

  it('sends the signed campaign value from the link, not anything typed', async () => {
    const user = userEvent.setup();
    renderForm('/lead-form/preview?campaign=signed.value&referral_code=AB12CD34');
    expect(screen.getByRole('textbox', { name: 'Referral code' })).toHaveValue('AB12CD34');
    await user.type(screen.getByRole('textbox', { name: /Name/ }), 'Asha');
    await user.type(screen.getByRole('textbox', { name: 'Phone' }), '9876543210');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    expect(submitPublicLead).toHaveBeenCalledWith('preview', expect.objectContaining({
      name: 'Asha',
      phone: '9876543210',
      campaign: 'signed.value',
      referral_code: 'AB12CD34',
    }));
  });

  it('sends an empty campaign when the link has none', async () => {
    const user = userEvent.setup();
    renderForm();
    await user.type(screen.getByRole('textbox', { name: /Name/ }), 'Asha');
    await user.type(screen.getByRole('textbox', { name: 'Phone' }), '9876543210');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    expect(submitPublicLead).toHaveBeenCalledWith('preview', expect.objectContaining({ campaign: '' }));
  });
});
