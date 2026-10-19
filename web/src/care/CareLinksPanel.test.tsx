import { screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderRoutes } from '@/test/careHarness';
import { CareLinksPanel } from './CareLinksPanel';

const flags = vi.hoisted(() => ({ on: true }));
vi.mock('@/config/features', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/config/features')>()),
  isSupportTicketsEnabled: () => flags.on,
  isComplaintsEnabled: () => false,
  isContractsEnabled: () => false,
  isWorkshopEnabled: () => false,
  isProjectsEnabled: () => false,
}));
const links = vi.hoisted(() => vi.fn());
vi.mock('@/api/care', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/care')>()),
  recordLinks: (...args: unknown[]) => links(...args),
}));

function panel(always = false, entity: 'customer' | 'invoice' = 'invoice') {
  return renderRoutes([{ path: '/', element: <CareLinksPanel entity={entity} id={5} always={always} /> }], '/');
}

beforeEach(() => {
  vi.clearAllMocks();
  flags.on = true;
  links.mockResolvedValue([{ kind: 'ticket', id: 1, number: 'TKT-1', status: 'OPEN', href: '/support/tickets/1', label: 'Noise' }]);
});

describe('CareLinksPanel', () => {
  it('lists what is tied to an invoice', async () => {
    panel();
    expect(await screen.findByRole('link', { name: /Ticket TKT-1/ })).toHaveAttribute('href', '/support/tickets/1');
    expect(links).toHaveBeenCalledWith('invoice', 5);
  });

  it('stays quiet on an invoice that has nothing linked', async () => {
    links.mockResolvedValue([]);
    const view = panel();
    await vi.waitFor(() => expect(links).toHaveBeenCalled());
    expect(view.container).toBeEmptyDOMElement();
  });

  it('always shows for a customer, even with nothing linked', async () => {
    links.mockResolvedValue([]);
    panel(true, 'customer');
    expect(await screen.findByText('Nothing is linked to this record yet.')).toBeInTheDocument();
  });

  it('does not even ask when every care module is off', () => {
    flags.on = false;
    const view = panel();
    expect(links).not.toHaveBeenCalled();
    expect(view.container).toBeEmptyDOMElement();
  });
});
