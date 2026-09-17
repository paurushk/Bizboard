import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { t } from '@/i18n';
import { ContextHelp } from './ContextHelp';
import { PageTitle } from './PageTitle';
import { getContextHelpPage, listContextHelpPageIds } from './catalog';
import { CONTEXT_HELP_ROUTES, resolveContextHelpPage } from './routes';

function LocationProbe() {
  const loc = useLocation();
  return <div data-testid="path">{loc.pathname}</div>;
}

describe('context help catalog', () => {
  it('has unique ids, unique titles, and required sections', () => {
    const ids = listContextHelpPageIds();
    expect(new Set(ids).size).toBe(ids.length);
    expect(ids.length).toBeGreaterThan(40);
    expect(ids).not.toContain('generic-ops');
    expect(ids).not.toContain('gst-return');
    const titles = ids.map((id) => getContextHelpPage(id)!.title.en);
    expect(new Set(titles).size).toBe(titles.length);
    for (const id of ids) {
      const page = getContextHelpPage(id);
      expect(page, id).toBeTruthy();
      expect(page!.title.en.length).toBeGreaterThan(0);
      expect(page!.summary.en.length).toBeGreaterThan(0);
      expect(page!.howItWorks.length).toBeGreaterThan(0);
      expect(page!.businessImpact.length).toBeGreaterThan(0);
      expect(page!.keyRules.length).toBeGreaterThan(0);
      expect(page!.commonMistakes.length).toBeGreaterThan(0);
      expect(page!.relatedPages.length).toBeGreaterThan(0);
      expect(page!.nextActions.length).toBeGreaterThan(0);
      for (const rel of page!.relatedPages) {
        expect(t(rel.labelKey), `${id} → ${rel.labelKey}`).not.toBe(rel.labelKey);
      }
    }
  });

  it('covers every routed screen and has no unmapped catalog leftover', () => {
    const catalog = new Set(listContextHelpPageIds());
    const routed = new Set(CONTEXT_HELP_ROUTES.map((row) => row.id));
    for (const row of CONTEXT_HELP_ROUTES) {
      expect(resolveContextHelpPage(row.example), row.example).toBe(row.id);
      expect(catalog.has(row.id), `missing catalog for ${row.id}`).toBe(true);
    }
    for (const id of catalog) {
      expect(routed.has(id), `unmapped catalog id ${id}`).toBe(true);
    }
  });
});

describe('resolveContextHelpPage', () => {
  it('maps invoice editor and detail separately', () => {
    expect(resolveContextHelpPage('/sales/new')).toBe('sales-invoice');
    expect(resolveContextHelpPage('/sales/history/12/edit')).toBe('sales-invoice');
    expect(resolveContextHelpPage('/sales/history/12')).toBe('sales-invoice-detail');
    expect(resolveContextHelpPage('/sales/history')).toBe('sales-history');
  });

  it('maps list vs editor for orders, challans and notes', () => {
    expect(resolveContextHelpPage('/sales/orders')).toBe('sales-orders');
    expect(resolveContextHelpPage('/sales/orders/new')).toBe('sales-order-editor');
    expect(resolveContextHelpPage('/sales/orders/9')).toBe('sales-order-editor');
    expect(resolveContextHelpPage('/sales/delivery-challans')).toBe('delivery-challans');
    expect(resolveContextHelpPage('/sales/delivery-challans/new')).toBe('delivery-challan-editor');
    expect(resolveContextHelpPage('/sales/credit-notes')).toBe('sales-credit-notes');
    expect(resolveContextHelpPage('/sales/credit-notes/3')).toBe('sales-credit-note-editor');
    expect(resolveContextHelpPage('/purchases/orders')).toBe('purchase-orders');
    expect(resolveContextHelpPage('/purchases/orders/new')).toBe('purchase-order-editor');
    expect(getContextHelpPage('sales-orders')!.title.en).not.toBe(
      getContextHelpPage('sales-order-editor')!.title.en,
    );
  });

  it('maps purchase and GST worksheets per screen', () => {
    expect(resolveContextHelpPage('/purchases/new')).toBe('purchase-invoice');
    expect(resolveContextHelpPage('/reports/gstr1')).toBe('gstr-1');
    expect(resolveContextHelpPage('/reports/gstr3b')).toBe('gstr-3b');
    expect(resolveContextHelpPage('/reports/gstr2b')).toBe('gstr-2b');
    expect(resolveContextHelpPage('/reports/trial-balance')).toBe('trial-balance');
    expect(resolveContextHelpPage('/insights/alerts')).toBe('insights-alerts');
    expect(resolveContextHelpPage('/insights')).toBe('insights');
    expect(resolveContextHelpPage('/manufacturing/boms')).toBe('manufacturing-boms');
    expect(resolveContextHelpPage('/payroll/pay-runs')).toBe('payroll-pay-runs');
    expect(resolveContextHelpPage('/crm/leads')).toBe('crm-leads');
    expect(resolveContextHelpPage('/')).toBe('dashboard');
    expect(getContextHelpPage('gstr-1')!.title.en).not.toBe(getContextHelpPage('gstr-3b')!.title.en);
  });

  it('does not attach page help on the FAQ page', () => {
    expect(resolveContextHelpPage('/help')).toBeUndefined();
  });
});

describe('ContextHelp drawer', () => {
  it('opens and closes without changing the route', async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={['/sales/new']}>
        <Routes>
          <Route
            path="/sales/new"
            element={
              <>
                <PageTitle>Create invoice</PageTitle>
                <button type="button">Save & Complete</button>
                <LocationProbe />
              </>
            }
          />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByRole('heading', { name: 'Create invoice' })).toBeInTheDocument();
    const complete = screen.getByRole('button', { name: 'Save & Complete' });
    expect(complete).toBeEnabled();

    await user.click(screen.getByTestId('context-help-trigger'));
    const drawer = await screen.findByTestId('context-help-drawer');
    expect(drawer).toHaveTextContent('Sales invoice');
    expect(drawer).toHaveTextContent('What this page is for');
    expect(screen.getByTestId('path')).toHaveTextContent('/sales/new');

    await user.click(screen.getByRole('button', { name: 'Close' }));
    expect(screen.getByTestId('context-help-trigger')).toHaveAttribute('aria-expanded', 'false');
    expect(screen.getByTestId('path')).toHaveTextContent('/sales/new');
    expect(complete).toBeEnabled();
  });

  it('renders nothing when the page has no catalog entry', () => {
    render(
      <MemoryRouter initialEntries={['/help']}>
        <ContextHelp />
      </MemoryRouter>,
    );
    expect(screen.queryByTestId('context-help-trigger')).not.toBeInTheDocument();
  });
});
