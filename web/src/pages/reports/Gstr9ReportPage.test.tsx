import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { Gstr9ReportPage } from './Gstr9ReportPage';

// QOS-0127: the annual return filing date feeds the Section 34(2) credit note limit.
vi.mock('@/auth/AuthContext', () => ({ useAuth: () => ({ user }) }));
vi.mock('@/components/GstHonestyHeader', () => ({ GstHonestyHeader: () => null }));

const filing = { filedOn: null as string | null };
const setGstr9FilingDate = vi.fn(async (fy: string, filedOn: string | null) => ({
  fy, filedOn, noteDeadline: filedOn ?? '2026-11-30',
}));
const user: Record<string, unknown> = { id: 1, email: 'o@x.test', fullName: 'O', role: 'OWNER', companyId: 1 };
vi.mock('@/api/resources', () => ({
  getGstr9: async () => ({ annual: {}, tables: {} }),
  downloadGstr9: vi.fn(),
  getGstr9FilingDate: async (fy: string) => ({ fy, filedOn: filing.filedOn, noteDeadline: filing.filedOn ?? '2026-11-30' }),
  setGstr9FilingDate: (fy: string, filedOn: string | null) => setGstr9FilingDate(fy, filedOn),
}));

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <Gstr9ReportPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('Gstr9ReportPage filing date', () => {
  beforeEach(() => {
    filing.filedOn = null;
    setGstr9FilingDate.mockClear();
  });

  it('shows a recorded date and clears it with null', async () => {
    filing.filedOn = '2026-10-15';
    renderPage();
    const input = (await screen.findByLabelText(/annual return filed on/i)) as HTMLInputElement;
    await waitFor(() => expect(input.value).toBe('2026-10-15'));
    const save = screen.getByRole('button', { name: /^save$/i }) as HTMLButtonElement;
    expect(save.disabled).toBe(true);
    await userEvent.clear(input);
    await waitFor(() => expect(save.disabled).toBe(false));
    await userEvent.click(save);
    await waitFor(() => expect(setGstr9FilingDate).toHaveBeenCalledWith(expect.any(String), null));
  });

  it('shows the server error when saving fails', async () => {
    setGstr9FilingDate.mockRejectedValueOnce(new Error('An annual return cannot be filed before the financial year ends.'));
    renderPage();
    const input = (await screen.findByLabelText(/annual return filed on/i)) as HTMLInputElement;
    await userEvent.type(input, '2026-01-01');
    await userEvent.click(screen.getByRole('button', { name: /^save$/i }));
    expect(await screen.findByText(/cannot be filed before the financial year ends/i)).toBeTruthy();
  });

  it('starts a fresh draft when the financial year changes', async () => {
    renderPage();
    const input = (await screen.findByLabelText(/annual return filed on/i)) as HTMLInputElement;
    await userEvent.type(input, '2026-10-15');
    expect(input.value).toBe('2026-10-15');
    const fy = screen.getByLabelText(/financial year|^fy/i) as HTMLInputElement;
    await userEvent.clear(fy);
    await userEvent.type(fy, '2024-25');
    await waitFor(() => expect((screen.getByLabelText(/annual return filed on/i) as HTMLInputElement).value).toBe(''));
  });

  it('saves the date the annual return was filed', async () => {
    renderPage();
    const input = (await screen.findByLabelText(/annual return filed on/i)) as HTMLInputElement;
    expect(await screen.findByText(/current credit note limit: 2026-11-30/i)).toBeTruthy();
    const save = screen.getByRole('button', { name: /^save$/i }) as HTMLButtonElement;
    expect(save.disabled).toBe(true);
    await userEvent.type(input, '2026-10-15');
    await waitFor(() => expect(save.disabled).toBe(false));
    await userEvent.click(save);
    await waitFor(() => expect(setGstr9FilingDate).toHaveBeenCalledWith(expect.stringMatching(/^\d{4}-\d{2}$/), '2026-10-15'));
  });
});
