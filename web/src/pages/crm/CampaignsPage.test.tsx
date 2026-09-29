import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { CampaignsPage } from '@/pages/crm/CampaignsPage';
import type { Campaign, Funnel } from '@/api/growth';

vi.mock('@/pages/erp/erpShared', () => ({
  ModuleGate: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

const { createCampaign, getCampaignFunnel, listCampaignsPage } = vi.hoisted(() => {
  const campaign: Campaign = {
    id: 1,
    name: 'Diwali',
    campaignType: 'DIGITAL',
    status: 'ACTIVE',
    parent: null,
    budget: '1000.00',
    targetRevenue: null,
    expectedOutcome: '',
    startDate: null,
    endDate: null,
  };
  const funnel: Funnel = {
    leads: 4,
    opportunities: 2,
    wonOpportunities: 1,
    budget: '1000.00',
    revenue: '650.00',
    targetRevenue: null,
    roiRatio: '0.6500',
    variance: '-350.00',
    rows: [{ opportunity: 9, revenueSource: 'opportunity_amount', revenue: '650.00' }],
  };
  return {
    createCampaign: vi.fn(async () => campaign),
    getCampaignFunnel: vi.fn(async () => funnel),
    listCampaignsPage: vi.fn(async () => ({ results: [campaign], count: 1, next: null, previous: null })),
  };
});

vi.mock('@/api/growth', () => ({
  listCampaignsPage: (...args: unknown[]) => listCampaignsPage(...args),
  createCampaign: (...args: unknown[]) => createCampaign(...args),
  updateCampaign: vi.fn(),
  deleteCampaign: vi.fn(),
  getCampaignFunnel: (...args: unknown[]) => getCampaignFunnel(...args),
}));

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/crm/campaigns']}>
        <Routes>
          <Route path="/crm/campaigns" element={<CampaignsPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('CampaignsPage', () => {
  it('lists campaigns and creates a new one with the expected payload', async () => {
    const user = userEvent.setup();
    wrap();
    expect(await screen.findByText(/Diwali · DIGITAL · ACTIVE/)).toBeInTheDocument();

    await user.type(screen.getByLabelText('Name'), 'Holi');
    await user.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(createCampaign).toHaveBeenCalledWith(
      expect.objectContaining({
        name: 'Holi',
        campaign_type: 'DIGITAL',
        status: 'DRAFT',
        parent: null,
        budget: '0',
      }),
    ));
  });

  it('loads and displays the funnel, including the rollup section, on demand', async () => {
    const user = userEvent.setup();
    wrap();
    await user.click(await screen.findByRole('button', { name: 'Funnel' }));

    await waitFor(() => expect(getCampaignFunnel).toHaveBeenCalledWith(1));
    expect(await screen.findByText(/Leads: 4/)).toBeInTheDocument();
    expect(screen.getByText(/Revenue: 650.00/)).toBeInTheDocument();
    expect(screen.getByText(/ROI 0.6500/)).toBeInTheDocument();
  });
});
