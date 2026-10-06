import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { CrmOnboardingPage } from '@/pages/crm/CrmOnboardingPage';

const state = vi.hoisted(() => ({
  mode: 'steps' as 'steps' | 'empty' | 'slow' | 'fail',
}));

vi.mock('@/api/osPlan', () => ({
  getCrmOnboarding: async () => {
    if (state.mode === 'slow') return new Promise(() => {});
    if (state.mode === 'fail') throw new Error('Onboarding service unavailable');
    if (state.mode === 'empty') return { steps: [] };
    return { steps: [{ id: 'lead', title: 'Capture your first lead', done: true }] };
  },
}));

vi.mock('@/contextHelp', () => ({ PageTitle: ({ children }: { children: string }) => <h1>{children}</h1> }));

function wrap() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <CrmOnboardingPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('CrmOnboardingPage states', () => {
  it('shows the steps once loaded', async () => {
    state.mode = 'steps';
    wrap();
    expect(await screen.findByText(/Capture your first lead/)).toBeTruthy();
  });

  it('shows a loading indicator while the checklist loads', async () => {
    state.mode = 'slow';
    wrap();
    expect(await screen.findByRole('progressbar')).toBeTruthy();
  });

  it('says so when there are no steps', async () => {
    state.mode = 'empty';
    wrap();
    expect(await screen.findByText('No onboarding steps yet.')).toBeTruthy();
  });

  it('shows an error with a retry when the checklist fails', async () => {
    state.mode = 'fail';
    wrap();
    await waitFor(() => expect(screen.getByText(/Onboarding service unavailable/)).toBeTruthy());
    expect(screen.getByRole('button', { name: /try again|retry/i })).toBeTruthy();
  });
});
