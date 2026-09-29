import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import type { ReactElement } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { advisorBook } from '@/api/roadmap';
import { isInsuranceEnabled } from '@/config/features';
import { InsurancePage } from '@/pages/insurance/InsurancePage';

vi.mock('@/config/features', () => ({ isInsuranceEnabled: vi.fn(() => false) }));
vi.mock('@/pages/growth/widgets', () => ({
  CustomerField: () => null,
  localDateInput: () => '2026-09-26',
}));
vi.mock('@/api/roadmap', () => ({
  listPolicyProducts: vi.fn().mockResolvedValue({ results: [] }),
  createPolicyProduct: vi.fn(),
  advisorBook: vi.fn().mockResolvedValue({ policies: [] }),
  createProspect: vi.fn(),
  createOptionSet: vi.fn(),
  chooseOption: vi.fn(),
  issuePolicy: vi.fn(),
}));

function wrap(ui: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('InsurancePage', () => {
  it('explains that the module is off', () => {
    vi.mocked(isInsuranceEnabled).mockReturnValue(false);
    wrap(<InsurancePage />);
    expect(screen.getByText(/isn’t enabled/i)).toBeTruthy();
  });

  it('shows the in-force heading when the module is on and the book is empty', async () => {
    vi.mocked(isInsuranceEnabled).mockReturnValue(true);
    wrap(<InsurancePage />);
    expect(await screen.findByText('In force')).toBeTruthy();
  });

  it('shows the policy end date', async () => {
    vi.mocked(isInsuranceEnabled).mockReturnValue(true);
    vi.mocked(advisorBook).mockResolvedValue({
      policies: [{ id: 1, number: 'POL-1', status: 'IN_FORCE', endDate: '2027-01-01' }],
      leads: [],
      campaigns: [],
    });
    wrap(<InsurancePage />);
    expect(await screen.findByText(/ends 2027-01-01/)).toBeTruthy();
  });
});
