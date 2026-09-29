import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import type { ReactElement } from 'react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { invoiceMilestone, listProjects } from '@/api/roadmap';
import { isProjectsEnabled } from '@/config/features';
import { ProjectsPage } from '@/pages/projects/ProjectsPage';

vi.mock('@/config/features', () => ({ isProjectsEnabled: vi.fn(() => false) }));
vi.mock('@/api/roadmap', () => ({
  listProjects: vi.fn().mockResolvedValue({ results: [] }),
  createProject: vi.fn(),
  addMilestone: vi.fn(),
  markMilestoneReady: vi.fn(),
  invoiceMilestone: vi.fn(),
  closeProject: vi.fn(),
}));
vi.mock('@/pages/growth/widgets', () => ({ CustomerField: () => null, ProductField: () => null }));

function Location() {
  const location = useLocation();
  return <div data-testid="loc">{location.pathname}</div>;
}

function wrap(ui: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/projects']}>
        <Routes>
          <Route path="/projects" element={ui} />
          <Route path="/sales/invoices/:id" element={<Location />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('ProjectsPage', () => {
  it('explains that the module is off', () => {
    vi.mocked(isProjectsEnabled).mockReturnValue(false);
    wrap(<ProjectsPage />);
    expect(screen.getByText(/isn’t enabled/i)).toBeTruthy();
  });

  it('shows create when the module is on and the list is empty', async () => {
    vi.mocked(isProjectsEnabled).mockReturnValue(true);
    wrap(<ProjectsPage />);
    expect(await screen.findByRole('button', { name: 'Create' })).toBeTruthy();
  });

  it('opens the invoice for the milestone that was posted', async () => {
    vi.mocked(isProjectsEnabled).mockReturnValue(true);
    vi.mocked(listProjects).mockResolvedValue({
      results: [{
        id: 1,
        number: 'PRJ-1',
        name: 'Site',
        status: 'OPEN',
        milestones: [
          { id: 10, name: 'Foundation', status: 'INVOICED', salesInvoice: 1 },
          { id: 11, name: 'Handover', status: 'READY' },
        ],
      }],
    });
    vi.mocked(invoiceMilestone).mockResolvedValue({
      milestones: [
        { id: 10, salesInvoice: 1 },
        { id: 11, salesInvoice: 2 },
      ],
    });
    wrap(<ProjectsPage />);
    fireEvent.click(await screen.findByRole('button', { name: 'Invoice' }));
    expect(await screen.findByTestId('loc')).toHaveTextContent('/sales/invoices/2');
  });

  it('keeps milestone drafts separate per project', async () => {
    vi.mocked(isProjectsEnabled).mockReturnValue(true);
    vi.mocked(listProjects).mockResolvedValue({
      results: [
        { id: 1, number: 'PRJ-1', name: 'Site', status: 'OPEN', milestones: [] },
        { id: 2, number: 'PRJ-2', name: 'Yard', status: 'OPEN', milestones: [] },
      ],
    });
    wrap(<ProjectsPage />);
    const fields = await screen.findAllByLabelText('Milestone');
    fireEvent.change(fields[0], { target: { value: 'Foundation' } });
    expect(fields[1]).toHaveValue('');
    expect(screen.getAllByRole('button', { name: 'Close' })).toHaveLength(2);
  });
});
