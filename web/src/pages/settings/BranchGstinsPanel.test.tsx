import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { BranchGstinsPanel } from '@/pages/settings/BranchGstinsPanel';

const row = {
  id: 7,
  gstin: '29AAAAA0000A1ZY',
  legal_name: 'North depot',
  state: 'Karnataka',
  is_primary: false,
  is_active: true,
};

const { listCompanyGstins, createCompanyGstin, updateCompanyGstin } = vi.hoisted(() => ({
  listCompanyGstins: vi.fn(async () => [row]),
  createCompanyGstin: vi.fn(async () => row),
  updateCompanyGstin: vi.fn(async () => row),
}));

vi.mock('@/api/resources', () => ({
  listCompanyGstins: () => listCompanyGstins(),
  createCompanyGstin: (...args: unknown[]) => createCompanyGstin(...args),
  updateCompanyGstin: (...args: unknown[]) => updateCompanyGstin(...args),
}));

vi.mock('@/components/StateSelect', () => ({
  StateSelect: ({
    label,
    value,
    onChange,
  }: {
    label: string;
    value: string;
    onChange: (value: string) => void;
  }) => <input aria-label={label} value={value} onChange={(e) => onChange(e.target.value)} />,
}));

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <BranchGstinsPanel />
    </QueryClientProvider>,
  );
}

describe('BranchGstinsPanel', () => {
  it('sets a row primary and edits its name', async () => {
    const user = userEvent.setup();
    wrap();
    expect(await screen.findByText(/29AAAAA0000A1ZY/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Set primary' }));
    await waitFor(() => expect(updateCompanyGstin).toHaveBeenCalledWith(7, { is_primary: true }));

    await user.click(screen.getByRole('button', { name: 'Edit' }));
    const dialog = await screen.findByRole('dialog');
    const name = within(dialog).getByLabelText('Branch business name');
    await user.clear(name);
    await user.type(name, 'South depot');
    await user.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(updateCompanyGstin).toHaveBeenCalledWith(7, {
      gstin: '29AAAAA0000A1ZY',
      legal_name: 'South depot',
      state: 'Karnataka',
    }));
  });

  it('shows the create error instead of failing silently', async () => {
    createCompanyGstin.mockRejectedValueOnce(new Error('duplicate GSTIN'));
    const user = userEvent.setup();
    wrap();
    await screen.findByText(/29AAAAA0000A1ZY/);
    await user.type(screen.getByLabelText('Branch GSTIN'), '27AAPFU0939F1ZV');
    await user.click(screen.getByRole('button', { name: 'Add branch GSTIN' }));
    expect(await screen.findByText('duplicate GSTIN')).toBeInTheDocument();
  });
});
