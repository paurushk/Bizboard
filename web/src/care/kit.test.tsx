import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { a11yViolations, setViewport } from '@/test/careHarness';
import { canChangeCare, conflictInfo, useListPath, useNotice, useUrlFilters } from './hooks';
import { CareTable, MasterDetail, Pager, SearchField, SlaChip, StatusPill, VisuallyHidden, type CareColumn } from './kit';

type Row = { id: number; name: string; status: string };
const rows: Row[] = [
  { id: 1, name: 'First', status: 'OPEN' },
  { id: 2, name: 'Second', status: 'CLOSED' },
];
const columns: CareColumn<Row>[] = [
  { key: 'name', header: 'Name', primary: true, render: (row) => row.name },
  { key: 'status', header: 'State', render: (row) => <StatusPill group="ticketStatus" value={row.status} /> },
];

function Probe() {
  const location = useLocation();
  const { values, set } = useUrlFilters({ q: '', status: '', page: '1' });
  return (
    <div>
      <output aria-label="search">{location.search}</output>
      <output aria-label="values">{JSON.stringify(values)}</output>
      <button onClick={() => set({ q: 'abc', page: '3' })}>page3</button>
      <button onClick={() => set({ status: 'OPEN' })}>filter</button>
      <button onClick={() => set({ q: '' })}>clear</button>
    </div>
  );
}

function wrap(ui: React.ReactElement, initial = '/x') {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[initial]}>
        <Routes>
          <Route path="*" element={ui} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => setViewport(1280));

describe('useUrlFilters', () => {
  it('reads defaults, writes only what differs from them, and returns to page 1 on a new filter', async () => {
    const user = userEvent.setup();
    wrap(<Probe />, '/x?page=4&q=zed');
    expect(screen.getByLabelText('values')).toHaveTextContent('"q":"zed"');
    expect(screen.getByLabelText('values')).toHaveTextContent('"page":"4"');
    await user.click(screen.getByText('filter'));
    expect(screen.getByLabelText('search')).toHaveTextContent('?q=zed&status=OPEN');
    await user.click(screen.getByText('page3'));
    expect(screen.getByLabelText('search')).toHaveTextContent('page=3');
    await user.click(screen.getByText('clear'));
    expect(screen.getByLabelText('search')).not.toHaveTextContent('q=');
  });
});

describe('useListPath', () => {
  it('keeps the current query string on the way to a record', () => {
    function Path() {
      const path = useListPath('/support/tickets');
      const target = path('/7');
      return <output aria-label="target">{`${target.pathname}${target.search}`}</output>;
    }
    wrap(<Path />, '/support/tickets?status=OPEN&page=2');
    expect(screen.getByLabelText('target')).toHaveTextContent('/support/tickets/7?status=OPEN&page=2');
  });
});

describe('CareTable', () => {
  const href = (row: Row) => ({ pathname: `/r/${row.id}`, search: '?a=1' });

  it('is a labelled table with column headers and a link on the primary cell', async () => {
    const view = wrap(<CareTable caption="Things" columns={columns} rows={rows} rowKey={(r) => r.id} rowHref={href} />);
    expect(screen.getByRole('table', { name: 'Things' })).toBeInTheDocument();
    expect(screen.getAllByRole('columnheader').map((h) => h.textContent)).toEqual(['Name', 'State']);
    expect(screen.getByRole('link', { name: 'First' })).toHaveAttribute('href', '/r/1?a=1');
    expect(await a11yViolations(view.container)).toEqual([]);
  });

  it('turns into linked cards on a phone', () => {
    setViewport(400);
    wrap(<CareTable caption="Things" columns={columns} rows={rows} rowKey={(r) => r.id} rowHref={href} />);
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
    expect(screen.getAllByRole('link')).toHaveLength(2);
    expect(screen.getAllByText('State')).toHaveLength(2);
  });
});

describe('Pager', () => {
  it('shows nothing for one page, and steps through many', async () => {
    const onPage = vi.fn();
    const user = userEvent.setup();
    const { rerender } = wrap(<Pager page={1} count={10} pageSize={20} onPage={onPage} />);
    expect(screen.queryByRole('navigation')).not.toBeInTheDocument();
    rerender(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter><Pager page={2} count={65} pageSize={20} onPage={onPage} /></MemoryRouter>
      </QueryClientProvider>,
    );
    expect(screen.getByText('Page 2 of 4 · 65 results')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Next' }));
    expect(onPage).toHaveBeenCalledWith(3);
    await user.click(screen.getByRole('button', { name: 'Previous' }));
    expect(onPage).toHaveBeenCalledWith(1);
  });
});

describe('SearchField', () => {
  it('waits for a pause in typing before it calls back', async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    wrap(<SearchField value="" onChange={onChange} />);
    await user.type(screen.getByRole('searchbox'), 'abc');
    expect(onChange).not.toHaveBeenCalledWith('a');
    await waitFor(() => expect(onChange).toHaveBeenCalledWith('abc'));
    expect(onChange).toHaveBeenCalledTimes(1);
  });
});

describe('MasterDetail', () => {
  const back = { pathname: '/list', search: '?q=1' };

  it('shows list and detail side by side on a wide screen', () => {
    wrap(<MasterDetail list={<p>the list</p>} detail={<p>the detail</p>} hasSelection backTo={back} detailLabel="Details" />);
    expect(screen.getByText('the list')).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Details' })).toHaveTextContent('the detail');
  });

  it('shows one at a time on a phone, with a way back that keeps the filters', () => {
    setViewport(400);
    wrap(<MasterDetail list={<p>the list</p>} detail={<p>the detail</p>} hasSelection backTo={back} detailLabel="Details" />);
    expect(screen.queryByText('the list')).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Back to the list' })).toHaveAttribute('href', '/list?q=1');
  });
});

describe('chips', () => {
  it('names the status in words', () => {
    wrap(<StatusPill group="contractStatus" value="EXPIRING" />);
    expect(screen.getByText('Expiring soon')).toBeInTheDocument();
  });

  it('writes each SLA verdict as words and says nothing for none', () => {
    const { container, rerender } = wrap(<SlaChip state="breached" remainingSeconds={-3600} />);
    expect(screen.getByText('Past due by 1h')).toBeInTheDocument();
    rerender(<MemoryRouter><SlaChip state="met" remainingSeconds={60} /></MemoryRouter>);
    expect(screen.getByText('Resolved within the target')).toBeInTheDocument();
    rerender(<MemoryRouter><SlaChip state="none" remainingSeconds={null} /></MemoryRouter>);
    expect(container).toBeEmptyDOMElement();
  });

  it('hides text visually but keeps it for screen readers', () => {
    wrap(<button><VisuallyHidden>Actions</VisuallyHidden></button>);
    expect(screen.getByRole('button', { name: 'Actions' })).toBeInTheDocument();
  });
});

describe('notices and errors', () => {
  it('shows a success politely and a failure as an alert', async () => {
    function Demo() {
      const feedback = useNotice();
      return (
        <div>
          <button onClick={() => feedback.ok('Saved.')}>ok</button>
          <button onClick={() => feedback.fail(new Error('boom'))}>fail</button>
          {feedback.node}
        </div>
      );
    }
    const user = userEvent.setup();
    wrap(<Demo />);
    await user.click(screen.getByText('ok'));
    expect(screen.getByRole('status')).toHaveTextContent('Saved.');
    await user.click(screen.getByText('fail'));
    expect(screen.getByRole('alert')).toBeInTheDocument();
  });

  it('reads a conflict code out of an API answer, and nothing from other errors', () => {
    const conflict = Object.assign(new Error('x'), {
      isAxiosError: true,
      response: { status: 409, data: { error: { details: { code: 'overlap', message: 'Overlaps CON-1', overlaps: ['CON-1'] } } } },
    });
    expect(conflictInfo(conflict)).toMatchObject({ code: 'overlap', message: 'Overlaps CON-1' });
    expect(conflictInfo(new Error('plain'))).toBeNull();
    const other = Object.assign(new Error('x'), { isAxiosError: true, response: { status: 400, data: {} } });
    expect(conflictInfo(other)).toBeNull();
  });
});

describe('canChangeCare', () => {
  it('lets owners and people with the right change records, and never a viewer', () => {
    expect(canChangeCare({ role: 'OWNER' })).toBe(true);
    expect(canChangeCare({ role: 'SALES_STAFF', canCreateSales: true })).toBe(true);
    expect(canChangeCare({ role: 'SALES_STAFF', canCreateSales: false })).toBe(false);
    expect(canChangeCare({ role: 'VIEWER', canCreateSales: true })).toBe(false);
    expect(canChangeCare(null)).toBe(false);
    expect(canChangeCare({ role: 'ACCOUNTANT', canCreatePurchases: true }, 'purchases')).toBe(true);
    expect(canChangeCare({ role: 'SALES_STAFF', canCreateSales: true }, 'purchases')).toBe(false);
  });
});
