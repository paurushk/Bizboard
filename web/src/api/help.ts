import { apiClient, shouldUseMocks, unwrapData } from '@/api/client';

export async function postHelpEvents(events: Record<string, unknown>[]): Promise<void> {
  if (shouldUseMocks() || events.length === 0) return;
  await apiClient.post('/help-events/', { events });
}

export async function postHelpFeedback(body: {
  query?: string;
  screen?: string;
  intentId?: string;
  note?: string;
}): Promise<{ id: number }> {
  if (shouldUseMocks()) return { id: 0 };
  const { data } = await apiClient.post('/help-feedback/', body);
  return unwrapData<{ id: number }>(data);
}

export type HelpHealthPayload = {
  windowDays: number;
  scope: string;
  resolutionRate: number | null;
  escalationRate: number | null;
  repeatQueryRate: number | null;
  timeToResolutionSeconds: number | null;
  opens: number;
  rated: number;
  resolved: number;
  understoodPending: number;
  unresolved: number;
  feedbackOpen: number;
  searchCount: number;
  zeroResultCount: number;
  zeroResultRate: number | null;
  topZeroQueries: { query: string; n: number }[];
  intents: Array<{
    intentId: string;
    opens: number;
    resolved: number;
    unresolved: number;
    searches: number;
    resolutionRate: number | null;
    timeToResolutionSeconds?: number | null;
  }>;
  repeatQueries: { query: string; n: number }[];
  escalationCount: number;
};

export async function getHelpHealth(all = false): Promise<HelpHealthPayload> {
  if (shouldUseMocks()) {
    return {
      windowDays: 30,
      scope: all ? 'all' : 'company',
      resolutionRate: null,
      escalationRate: null,
      repeatQueryRate: null,
      timeToResolutionSeconds: null,
      opens: 0,
      rated: 0,
      resolved: 0,
      understoodPending: 0,
      unresolved: 0,
      feedbackOpen: 0,
      searchCount: 0,
      zeroResultCount: 0,
      zeroResultRate: null,
      topZeroQueries: [],
      intents: [],
      repeatQueries: [],
      escalationCount: 0,
    };
  }
  const { data } = await apiClient.get('/help-health/', { params: all ? { all: 1 } : undefined });
  return unwrapData<HelpHealthPayload>(data);
}

export async function resolveHelpFeedback(id: number, all = false): Promise<void> {
  if (shouldUseMocks()) return;
  await apiClient.patch('/help-feedback/', { id }, { params: all ? { all: 1 } : undefined });
}

export async function listHelpFeedback(all = false): Promise<
  Array<{
    id: number;
    company: number;
    companyName: string;
    query: string;
    screen: string;
    role: string;
    intentId: string;
    note: string;
    createdAt: string | null;
  }>
> {
  if (shouldUseMocks()) return [];
  const { data } = await apiClient.get('/help-feedback/', { params: all ? { all: 1 } : undefined });
  const body = unwrapData<{ results?: Array<Record<string, unknown>> }>(data);
  return (body.results ?? []).map((row) => ({
    id: Number(row.id),
    company: Number(row.company),
    companyName: String(row.companyName ?? row.company_name ?? ''),
    query: String(row.query ?? ''),
    screen: String(row.screen ?? ''),
    role: String(row.role ?? ''),
    intentId: String(row.intentId ?? row.intent_id ?? ''),
    note: String(row.note ?? ''),
    createdAt: (row.createdAt ?? row.created_at ?? null) as string | null,
  }));
}
