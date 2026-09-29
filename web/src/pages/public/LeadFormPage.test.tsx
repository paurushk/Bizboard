import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { submitPublicLead } from '@/api/osPlan';
import { LeadFormPage } from '@/pages/public/LeadFormPage';

vi.mock('@/api/osPlan', () => ({
  submitPublicLead: vi.fn().mockResolvedValue(undefined),
}));

function renderForm(entry = '/lead-form/preview') {
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <Routes>
        <Route path="/lead-form/:token" element={<LeadFormPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('LeadFormPage', () => {
  it('blocks a non-numeric campaign id and still sends a numeric one', async () => {
    const user = userEvent.setup();
    renderForm();
    await user.type(screen.getByRole('textbox', { name: /Name/ }), 'Asha');
    await user.type(screen.getByRole('textbox', { name: 'Phone' }), '9876543210');
    await user.type(screen.getByRole('textbox', { name: 'Campaign id' }), 'abc');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    expect(screen.getByText('Campaign id must be a number.')).toBeInTheDocument();
    expect(submitPublicLead).not.toHaveBeenCalled();

    await user.clear(screen.getByRole('textbox', { name: 'Campaign id' }));
    await user.type(screen.getByRole('textbox', { name: 'Campaign id' }), '12');
    await user.type(screen.getByRole('textbox', { name: 'Referral code' }), 'AB12CD34');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    expect(submitPublicLead).toHaveBeenCalledWith('preview', expect.objectContaining({
      name: 'Asha',
      phone: '9876543210',
      campaign: 12,
      referral_code: 'AB12CD34',
    }));
  });

  it('prefills campaign and referral code from the share link', async () => {
    const user = userEvent.setup();
    renderForm('/lead-form/preview?campaign=12&referral_code=AB12CD34');
    expect(screen.getByRole('textbox', { name: 'Campaign id' })).toHaveValue('12');
    expect(screen.getByRole('textbox', { name: 'Referral code' })).toHaveValue('AB12CD34');
    await user.type(screen.getByRole('textbox', { name: /Name/ }), 'Asha');
    await user.type(screen.getByRole('textbox', { name: 'Phone' }), '9876543210');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    expect(submitPublicLead).toHaveBeenCalledWith('preview', expect.objectContaining({
      campaign: 12,
      referral_code: 'AB12CD34',
    }));
  });
});
