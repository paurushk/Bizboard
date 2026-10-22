import { apiClient, idempotencyHeaders, newIdempotencyKey, unwrapData } from '@/api/client';
import { apiPath } from '@/api/typedClient';

const BASE = apiPath('/agents');

export type AgentRenderer = 'message' | 'lines' | 'comparison' | 'order' | 'unknown';

export type AgentProposalKindInfo = {
  kind: string;
  renderer: AgentRenderer;
  bulkApprovable: boolean;
  titleKey: string;
  canApprove: boolean;
};

export type AgentInfo = {
  kind: string;
  titleKey: string;
  triggerCodes: string[];
  canPrepare: boolean;
  proposalKinds: AgentProposalKindInfo[];
};

export type AgentCatalog = { agents: AgentInfo[] };

export type ProposalStatus =
  | 'PENDING'
  | 'APPROVED'
  | 'EXECUTED'
  | 'FAILED'
  | 'REJECTED'
  | 'CANCELLED'
  | 'EXPIRED';

export type AgentEvidence = {
  type: string;
  id: string | number;
  label: string;
  href?: string;
  fact?: unknown;
};

export type AgentProposal = {
  id: number;
  agent: string;
  kind: string;
  status: ProposalStatus;
  title: string;
  payload: Record<string, unknown>;
  schemaVersion: number;
  revision: number;
  evidence: AgentEvidence[];
  dedupeKey: string;
  groupKey: string;
  expiresAt: string;
  attempts: number;
  failureCode: string;
  decisionNote: string;
  resultRef: Record<string, unknown> | null;
  renderer: AgentRenderer;
  canApprove: boolean;
  bulkApprovable: boolean;
  createdAt: string;
};

export type AgentRunStatus =
  | 'QUEUED'
  | 'RUNNING'
  | 'SUCCEEDED'
  | 'FAILED'
  | 'TIMED_OUT'
  | 'BUDGET_EXCEEDED'
  | 'CANCELLED';

export type AgentRun = {
  id: number;
  agent: string;
  status: AgentRunStatus;
  errorCode: string;
  rulesOnly: boolean;
  proposalIds?: number[];
};

export type BulkApproveResult = { id: number; ok: boolean; status?: string; code?: string };

export const RUN_TERMINAL: AgentRunStatus[] = ['SUCCEEDED', 'FAILED', 'TIMED_OUT', 'BUDGET_EXCEEDED', 'CANCELLED'];

export async function getAgentCatalog(): Promise<AgentCatalog> {
  const { data } = await apiClient.get(`${BASE}/catalog/`);
  return unwrapData<AgentCatalog>(data);
}

/** Starts a run. A new Idempotency-Key per click: the same key is only for a network retry of that click. */
export async function startAgentRun(agent: string, triggerRef: string, key?: string): Promise<AgentRun> {
  const { data } = await apiClient.post(`${BASE}/runs/`, { agent, triggerRef }, { headers: idempotencyHeaders(key) });
  return unwrapData<AgentRun>(data);
}

/** Agents that read pasted text (Order Intake). The run is synchronous: the answer carries the draft's id. */
export async function startAgentTextRun(agent: string, text: string, key?: string): Promise<AgentRun> {
  const { data } = await apiClient.post(`${BASE}/runs/`, { agent, text }, { headers: idempotencyHeaders(key) });
  return unwrapData<AgentRun>(data);
}

export async function getAgentRun(id: number): Promise<AgentRun> {
  const { data } = await apiClient.get(`${BASE}/runs/${id}/`);
  return unwrapData<AgentRun>(data);
}

export async function listProposals(params?: {
  status?: string;
  kind?: string;
  dedupeKey?: string;
}): Promise<AgentProposal[]> {
  const { data } = await apiClient.get(`${BASE}/proposals/`, {
    params: { status: params?.status, kind: params?.kind, dedupe_key: params?.dedupeKey },
  });
  return unwrapData<{ results: AgentProposal[] }>(data).results;
}

export async function getProposal(id: number): Promise<AgentProposal> {
  const { data } = await apiClient.get(`${BASE}/proposals/${id}/`);
  return unwrapData<AgentProposal>(data);
}

export async function editProposal(
  id: number,
  editedPayload: Record<string, unknown>,
  revision: number,
): Promise<AgentProposal> {
  const { data } = await apiClient.patch(`${BASE}/proposals/${id}/`, { editedPayload, revision });
  return unwrapData<AgentProposal>(data);
}

/** One fresh key per user attempt: an edit, or a retry after a failure, must never reuse a stored answer. */
export async function approveProposal(id: number, revision: number, key: string = newIdempotencyKey()): Promise<AgentProposal> {
  const { data } = await apiClient.post(`${BASE}/proposals/${id}/approve/`, { revision }, { headers: idempotencyHeaders(key) });
  return unwrapData<AgentProposal>(data);
}

export async function retryProposal(id: number, revision: number, key: string = newIdempotencyKey()): Promise<AgentProposal> {
  const { data } = await apiClient.post(`${BASE}/proposals/${id}/retry/`, { revision }, { headers: idempotencyHeaders(key) });
  return unwrapData<AgentProposal>(data);
}

export async function rejectProposal(id: number, reason = ''): Promise<AgentProposal> {
  const { data } = await apiClient.post(`${BASE}/proposals/${id}/reject/`, { reason });
  return unwrapData<AgentProposal>(data);
}

export async function cancelProposal(id: number, note = ''): Promise<AgentProposal> {
  const { data } = await apiClient.post(`${BASE}/proposals/${id}/cancel/`, { note });
  return unwrapData<AgentProposal>(data);
}

export async function bulkApproveProposals(
  items: { id: number; revision: number }[],
  key: string = newIdempotencyKey(),
): Promise<BulkApproveResult[]> {
  const { data } = await apiClient.post(`${BASE}/proposals/bulk-approve/`, { items }, { headers: idempotencyHeaders(key) });
  return unwrapData<{ results: BulkApproveResult[] }>(data).results;
}
