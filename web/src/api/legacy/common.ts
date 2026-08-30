/** Shared legacy API helpers. */
import { apiClient, shouldUseMocks, unwrapData } from '../client';
import type { Paginated } from '@/types/domain';

export async function withMocks<T>(fn: () => Promise<T>, fallback: T | (() => T)): Promise<T> {
  if (shouldUseMocks()) {
    await sleep(150);
    return typeof fallback === 'function' ? (fallback as () => T)() : fallback;
  }
  return fn();
}

export function sleep(ms: number) {
  return new Promise((r) => setTimeout(r, ms));
}

export function asList<T>(data: Paginated<T> | T[] | null | undefined): T[] {
  if (Array.isArray(data)) return data;
  if (data && Array.isArray(data.results)) return data.results;
  return [];
}

export function getNextUrl(data: Paginated<unknown> | unknown[] | null | undefined): string | null {
  if (!data || Array.isArray(data)) return null;
  return data.next ?? null;
}

export type PageResult<T> = {
  results: T[];
  count: number;
  next: string | null;
  previous: string | null;
};

export function asPageResult<T>(body: Paginated<T> | T[] | null | undefined): PageResult<T> {
  if (Array.isArray(body)) {
    return { results: body, count: body.length, next: null, previous: null };
  }
  return {
    results: asList(body),
    count: typeof body?.count === 'number' ? body.count : asList(body).length,
    next: body?.next ?? null,
    previous: body?.previous ?? null,
  };
}

export type PageParams = {
  page?: number;
  pageSize?: number;
  q?: string;
  cf?: Record<string, string[]>;
  [key: string]: string | number | boolean | string[] | Record<string, string[]> | undefined | null;
};

export interface InvoiceNumberSeries {
  docType: string;
  prefix: string;
  nextNumber: number;
  padding: number;
  preview: string;
}

export function flattenQueryParams(params?: PageParams): Record<string, string | string[]> | undefined {
  if (!params) return undefined;
  const out: Record<string, string | string[]> = {};
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue;
    if (key === 'pageSize') {
      out.page_size = String(value);
      continue;
    }
    if (key === 'cf' && typeof value === 'object' && !Array.isArray(value)) {
      for (const [field, items] of Object.entries(value as Record<string, string[]>)) {
        const cleaned = (items ?? []).map(String).filter(Boolean);
        if (cleaned.length) out[`cf.${field}`] = cleaned;
      }
      continue;
    }
    out[key] = Array.isArray(value) ? value.map(String) : String(value);
  }
  return Object.keys(out).length ? out : undefined;
}

export function toQueryParams(params?: PageParams): Record<string, string | string[]> | undefined {
  return flattenQueryParams(params);
}

/** Page-number pagination helper (DRF PageNumberPagination). */
export async function fetchPage<T>(path: string, params?: PageParams): Promise<PageResult<T>> {
  const { data } = await apiClient.get(path, {
    params: toQueryParams(params),
    paramsSerializer: { indexes: null },
  });
  return asPageResult(unwrapData<Paginated<T> | T[]>(data));
}

/** Fetch first page + optional cursor for load-more UIs. */
export async function listPage<T>(
  path: string,
  params?: PageParams,
): Promise<{ results: T[]; next: string | null }> {
  const page = await fetchPage<T>(path, params);
  return { results: page.results, next: page.next };
}

export async function fetchNextPage<T>(nextUrl: string): Promise<{ results: T[]; next: string | null }> {
  let path = nextUrl;
  try {
    const u = new URL(nextUrl, window.location.origin);
    const apiBase = (import.meta.env.VITE_API_BASE_URL || '').trim();
    const allowedOrigins = new Set<string>([window.location.origin]);
    if (apiBase.startsWith('http')) {
      allowedOrigins.add(new URL(apiBase).origin);
    }
    allowedOrigins.add('http://127.0.0.1:8000');
    allowedOrigins.add('http://localhost:8000');
    allowedOrigins.add('http://localhost');
    allowedOrigins.add('http://127.0.0.1');

    const currentHost = window.location.hostname;
    const isSameRootDomain = currentHost && (u.hostname === currentHost || u.hostname.endsWith(`.${currentHost}`));

    if (!allowedOrigins.has(u.origin) && !isSameRootDomain) {
      throw new Error('Blocked pagination next URL from unexpected host');
    }
    path = u.pathname.replace(/^\/api\/v1/, '') + u.search;
  } catch (e) {
    if (e instanceof Error && e.message.startsWith('Blocked')) throw e;
    path = nextUrl.replace(/^\/api\/v1/, '');
    if (/^https?:\/\//i.test(path)) {
      throw new Error('Blocked pagination next URL from unexpected host');
    }
  }
  const { data } = await apiClient.get(path);
  const body = unwrapData<Paginated<T> | T[]>(data);
  return { results: asList(body), next: getNextUrl(body) };
}

export async function fetchMoneyListFirstPage<T>(
  path: string,
  params?: Record<string, string>,
): Promise<T[]> {
  const page = await listPage<T>(path, params);
  return page.results;
}

export async function fetchAllPagesMasters<T>(
  path: string,
  params?: PageParams,
): Promise<T[]> {
  const first = await listPage<T>(path, params);
  let results = first.results;
  let next = first.next;
  const MAX_PAGES = 500;
  let guard = 0;
  while (next && guard < MAX_PAGES) {
    const page = await fetchNextPage<T>(next);
    results = results.concat(page.results);
    next = page.next;
    guard += 1;
  }
  return results;
}
