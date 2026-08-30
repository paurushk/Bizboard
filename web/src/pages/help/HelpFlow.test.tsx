import { render, screen } from '@testing-library/react';
import { act } from 'react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createMemoryRouter, MemoryRouter, RouterProvider } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ErrorState } from '@/components/PageState';
import { UniversalSearch } from '@/components/UniversalSearch';
import { HelpWhyLink } from './HelpWhyLink';
import { HelpEmptyLink } from './HelpEmptyLink';
import { HelpFeedbackForm } from './HelpFeedbackForm';
import { HelpHint, HelpIntentDrawer } from './HelpHint';
import { HelpPageV2 } from './HelpPageV2';
import { NextStepButton } from './NextStepButton';
import { PreventionNote } from './PreventionNote';
import { HELP_EVENTS, trackHelpEvent } from './analytics';
import { getHelpIntent } from './intents';

vi.mock('@/config/features', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/config/features')>();
  return { ...actual, isHelpV2Enabled: () => true };
});

vi.mock('@/api/resources', () => ({
  universalSearch: vi.fn(async () => []),
}));

vi.mock('./analytics', () => ({
  HELP_EVENTS: {
    OPEN: 'help_open',
    SEARCH: 'help_search',
    RESOLVED: 'faq_resolved',
    UNDERSTOOD: 'faq_understood_pending',
    UNRESOLVED: 'faq_unresolved',
    DIAGNOSIS_BRANCH: 'diagnosis_branch',
    PREVENTION_VIEW: 'prevention_view',
    NEXTSTEP: 'faq_nextstep_click',
  },
  trackHelpEvent: vi.fn(),
}));

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({
    user: {
      id: 1,
      email: 'o@x.test',
      fullName: 'Owner',
      role: 'OWNER',
      canCreateSales: true,
      canCancelDocuments: true,
      companyId: 1,
    },
  }),
}));

describe('Help Why? / empty / prevention / feedback', () => {
  beforeEach(() => {
    vi.mocked(trackHelpEvent).mockClear();
    sessionStorage.clear();
  });

  it('Why? on a leaf-named error skips the picker', () => {
    render(
      <MemoryRouter>
        <HelpWhyLink code="inactive_product" message="Cannot sell" invoiceId={12} />
      </MemoryRouter>,
    );
    const link = screen.getByRole('link', { name: /why/i });
    expect(link.getAttribute('href')).toContain('intent=sell-blocked');
    expect(link.getAttribute('href')).toContain('leaf=inactive');
    expect(link.getAttribute('href')).toContain('invoiceId=12');
    expect(link.getAttribute('href')).toContain('source=error');
  });

  it('empty-state link carries source=empty (page emits help_open)', () => {
    render(
      <MemoryRouter>
        <HelpEmptyLink intent="import-row-errors" />
      </MemoryRouter>,
    );
    expect(screen.getByRole('link').getAttribute('href')).toContain('source=empty');
    expect(screen.getByRole('link').getAttribute('href')).toContain('intent=import-row-errors');
  });

  it('prevention note emits prevention_view', async () => {
    await act(async () => {
      render(
        <MemoryRouter>
          <PreventionNote intent="cannot-complete-invoice" slot="invoice-complete" />
        </MemoryRouter>,
      );
    });
    expect(trackHelpEvent).toHaveBeenCalledWith(HELP_EVENTS.PREVENTION_VIEW, {
      slot: 'invoice-complete',
      intent: 'cannot-complete-invoice',
    });
  });

  it('Solved it emits once per session', async () => {
    const user = userEvent.setup();
    sessionStorage.setItem('help:fb:add-gstin:page', HELP_EVENTS.RESOLVED);
    await act(async () => {
      render(<HelpFeedbackForm intentId="add-gstin" />);
    });
    await user.click(screen.getByRole('button', { name: /solved it/i }));
    expect(trackHelpEvent).not.toHaveBeenCalled();
  });

  it('Complete fail → Why? → Solved it writes faq_resolved', async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <HelpWhyLink code="place_of_supply_unresolved" message="Need state" invoiceId={9} />
        <HelpFeedbackForm intentId="cannot-complete-invoice" />
      </MemoryRouter>,
    );
    const why = screen.getByRole('link', { name: /why/i });
    expect(why.getAttribute('href')).toContain('intent=cannot-complete-invoice');
    expect(why.getAttribute('href')).toContain('leaf=pos');
    expect(why.getAttribute('href')).toContain('source=error');
    await user.click(why);
    expect(trackHelpEvent).not.toHaveBeenCalledWith(
      HELP_EVENTS.OPEN,
      expect.anything(),
    );
    await user.click(screen.getByRole('button', { name: /solved it/i }));
    expect(trackHelpEvent).toHaveBeenCalledWith(HELP_EVENTS.RESOLVED, {
      intentId: 'cannot-complete-invoice',
      query: undefined,
    });
  });
});

describe('help_open sources + trap + back + cancel', () => {
  beforeEach(() => {
    vi.mocked(trackHelpEvent).mockClear();
    sessionStorage.clear();
  });

  it('ErrorState shows Why?', () => {
    render(
      <MemoryRouter>
        <ErrorState message="Cannot complete" />
      </MemoryRouter>,
    );
    expect(screen.getByRole('link', { name: /why/i })).toBeInTheDocument();
  });

  it('HelpHint emits help_open source=field', async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <HelpHint intent="add-gstin" slot="gstin">
          <span>GSTIN</span>
        </HelpHint>
      </MemoryRouter>,
    );
    await user.click(screen.getByRole('button', { name: /help for this field/i }));
    expect(trackHelpEvent).toHaveBeenCalledWith(HELP_EVENTS.OPEN, {
      source: 'field',
      intentId: 'add-gstin',
      slot: 'gstin',
    });
  });

  it('HelpHint wrap is a div, not a span', () => {
    render(
      <MemoryRouter>
        <HelpHint intent="add-gstin" slot="gstin">
          <span>GSTIN</span>
        </HelpHint>
      </MemoryRouter>,
    );
    const wrap = screen.getByTestId('help-hint-wrap');
    expect(wrap.tagName).toBe('DIV');
  });

  it('HelpPageV2 emits help_open source=nav', () => {
    act(() => {
      render(
        <MemoryRouter initialEntries={['/help']}>
          <HelpPageV2 />
        </MemoryRouter>,
      );
    });
    expect(trackHelpEvent).toHaveBeenCalledWith(HELP_EVENTS.OPEN, { source: 'nav', intentId: undefined });
  });

  it('HelpPageV2 emits help_open with the URL source on deep-link', () => {
    act(() => {
      render(
        <MemoryRouter initialEntries={['/help?intent=add-gstin&source=error']}>
          <HelpPageV2 />
        </MemoryRouter>,
      );
    });
    expect(trackHelpEvent).toHaveBeenCalledWith(HELP_EVENTS.OPEN, {
      source: 'error',
      intentId: 'add-gstin',
    });
  });

  it('back from an intent restores the search query', async () => {
    const user = userEvent.setup();
    const router = createMemoryRouter([{ path: '/help', element: <HelpPageV2 /> }], {
      initialEntries: ['/help'],
    });
    render(<RouterProvider router={router} />);
    await user.type(screen.getByLabelText(/what are you trying to do/i), 'gst');
    expect(router.state.location.search).toContain('q=gst');
    await user.click(screen.getByRole('button', { name: /add or change gstin/i }));
    expect(router.state.location.search).toContain('intent=add-gstin');
    await act(async () => {
      await router.navigate(-1);
    });
    expect(router.state.location.search).toContain('q=gst');
  });

  it('HelpIntentDrawer Tab wraps focus via MUI trap', async () => {
    const user = userEvent.setup();
    await act(async () => {
      render(
        <MemoryRouter>
          <HelpIntentDrawer open onClose={() => undefined} intentId="add-gstin" />
        </MemoryRouter>,
      );
    });
    const closeBtn = screen.getByRole('button', { name: /close/i });
    closeBtn.focus();
    expect(closeBtn).toHaveFocus();
    await user.tab({ shift: true });
    expect(closeBtn).not.toHaveFocus();
    await user.tab();
    expect(closeBtn).toHaveFocus();
  });

  it('Cancel this bill links to helpAction=cancel', async () => {
    const intent = getHelpIntent('edit-completed-invoice');
    render(
      <MemoryRouter>
        <NextStepButton nextStep={intent!.nextStep!} context={{ invoiceId: '1' }} />
      </MemoryRouter>,
    );
    expect(screen.getByRole('link', { name: /cancel this bill/i }).getAttribute('href')).toBe(
      '/sales/history/1?helpAction=cancel',
    );
    await userEvent.click(screen.getByRole('link', { name: /cancel this bill/i }));
    expect(trackHelpEvent).toHaveBeenCalledWith(
      HELP_EVENTS.NEXTSTEP,
      expect.objectContaining({ destination: '/sales/history/1?helpAction=cancel' }),
    );
  });

  it('Universal Search help hit emits source=search from HelpPage', async () => {
    const user = userEvent.setup();
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const router = createMemoryRouter(
      [
        {
          path: '/',
          element: (
            <QueryClientProvider client={qc}>
              <UniversalSearch />
            </QueryClientProvider>
          ),
        },
        { path: '/help', element: <HelpPageV2 /> },
      ],
      { initialEntries: ['/'] },
    );
    render(<RouterProvider router={router} />);
    await user.type(screen.getByRole('combobox', { name: /search invoices/i }), 'how do i add gstin');
    const option = await screen.findByRole('option', { name: /how do i add or change my gstin/i }, { timeout: 10000 });
    await user.click(option);
    expect(router.state.location.pathname).toBe('/help');
    expect(router.state.location.search).toContain('source=search');
    expect(trackHelpEvent).toHaveBeenCalledWith(HELP_EVENTS.OPEN, {
      source: 'search',
      intentId: 'add-gstin',
    });
  }, 20000);
});

