import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { CrmOnboardingPage } from '@/pages/crm/CrmOnboardingPage';

const { getCrmOnboarding } = vi.hoisted(() => ({
  getCrmOnboarding: vi.fn(async () => ({
    steps: [
      { id: 'import_leads', title: 'Import your existing leads', done: true },
      { id: 'create_campaign', title: 'Launch your first campaign', done: false },
      { id: 'close_deal', title: 'Convert lead to won opportunity', done: false },
    ],
  })),
}));

vi.mock('@/api/osPlan', () => ({
  getCrmOnboarding: () => getCrmOnboarding(),
}));

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/crm/onboarding']}>
        <Routes>
          <Route path="/crm/onboarding" element={<CrmOnboardingPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('CrmOnboardingPage', () => {
  it('renders onboarding steps checklist with completion status', async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByText(/Import your existing leads/i)).toBeInTheDocument();
    });

    expect(screen.getByText(/✓ Import your existing leads/)).toBeInTheDocument();
    expect(screen.getByText(/○ Launch your first campaign/)).toBeInTheDocument();
    expect(screen.getByText(/○ Convert lead to won opportunity/)).toBeInTheDocument();
  });
});
