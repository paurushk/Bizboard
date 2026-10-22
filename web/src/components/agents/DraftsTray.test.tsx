import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { AgentProposal } from '@/api/agents';
import * as api from '@/api/agents';
import { DraftsTray } from './DraftsTray';

vi.mock('@/api/agents', async (orig) => ({ ...(await orig<typeof import('@/api/agents')>()), listProposals: vi.fn() }));
vi.mock('@/config/featureFlags', () => ({ isRuntimeFlagEnabled: () => true, useFeatureFlagEpoch: () => 0 }));

function p(id: number, title: string, groupKey: string): AgentProposal {
  return {
    id, agent: 'INVENTORY_RISK', kind: 'STOCK_TRANSFER', status: 'PENDING', title, payload: {}, schemaVersion: 1, revision: 0,
    evidence: [], dedupeKey: `k${id}`, groupKey, expiresAt: '', attempts: 0, failureCode: '', decisionNote: '', resultRef: null,
    renderer: 'lines', canApprove: true, bulkApprovable: false, createdAt: '',
  };
}

describe('DraftsTray', () => {
  beforeEach(() => vi.resetAllMocks());

  it('keeps drafts of one group together and marks them linked', async () => {
    vi.mocked(api.listProposals).mockResolvedValue([
      p(1, 'Move stock A', 'INV:1:d'), p(2, 'Reminder X', ''), p(3, 'Reorder B', 'INV:1:d'),
    ]);
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter><DraftsTray /></MemoryRouter>
      </QueryClientProvider>,
    );
    await userEvent.click(await screen.findByRole('button', { name: /3 drafts waiting/ }));
    const titles = (await screen.findAllByRole('button')).map((b) => b.textContent ?? '').filter((x) => /Move|Reorder|Reminder/.test(x));
    expect(titles.map((x) => x.replace(/Linked drafts/, ''))).toEqual(['Move stock A', 'Reorder B', 'Reminder X']);
    expect(screen.getAllByText('Linked drafts')).toHaveLength(2);
  });
});
