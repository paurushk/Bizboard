import { apiClient, unwrapData } from '@/api/client';
import { fetchPage, type PageResult } from '@/api/resources';
import type { components } from '@/api/openapi-types';
import { apiPath } from '@/api/typedClient';

type Schemas = components extends { schemas: infer S } ? S : Record<string, never>;
type SchemaNamed<K extends string, Fallback> = K extends keyof Schemas ? Schemas[K] : Fallback;

export type StatutoryEvent = SchemaNamed<
  'StatutoryDocumentEvent',
  {
    id: number;
    entityType: string;
    entityId: number;
    eventType: string;
    payload: Record<string, unknown>;
    user?: number | null;
    userEmail?: string | null;
    createdAt: string;
  }
>;

const STATUTORY_PATH = apiPath('/statutory-events/');

export function listStatutoryEventsPage(params?: {
  entityType?: string;
  eventType?: string;
  page?: number;
  pageSize?: number;
}): Promise<PageResult<StatutoryEvent>> {
  return fetchPage<StatutoryEvent>(STATUTORY_PATH, {
    entity_type: params?.entityType,
    event_type: params?.eventType,
    page: params?.page,
    pageSize: params?.pageSize,
  });
}

export async function listStatutoryEvents(params?: {
  entityType?: string;
  eventType?: string;
}): Promise<StatutoryEvent[]> {
  const page = await listStatutoryEventsPage({ ...params, page: 1, pageSize: 50 });
  return page.results;
}

export async function getStatutoryEventsRaw() {
  const { data } = await apiClient.get(STATUTORY_PATH);
  return unwrapData(data);
}
