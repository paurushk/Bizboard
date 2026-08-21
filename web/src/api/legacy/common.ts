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
  [key: string]: string | number | boolean | undefined | null;
};

export interface InvoiceNumberSeries {
  docType: string;
  prefix: string;
  nextNumber: number;
  padding: number;
  preview: string;
}

export function toQueryParams(params?: PageParams): Record<string, string> | undefined {
  if (!params) return undefined;
  const out: Record<string, string> = {};
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue;
    if (key === 'pageSize') {
      out.page_size = String(value);
      continue;
    }
    out[key] = String(value);
  }
  return Object.keys(out).length ? out : undefined;
}

/** Page-number pagination helper (DRF PageNumberPagination). */
export async function fetchPage<T>(path: string, params?: PageParams): Promise<PageResult<T>> {
  const { data } = await apiClient.get(path, { params: toQueryParams(params) });
  return asPageResult(unwrapData<Paginated<T> | T[]>(data));
}

/** Fetch first page + optional cursor for load-more UIs. */
export async function listPage<T>(
  path: string,
  params?: Record<string, string>,
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
    if (!allowedOrigins.has(u.origin)) {
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
  params?: Record<string, string>,
): Promise<T[]> {
  const first = await listPage<T>(path, params);
  let results = first.results;
  let next = first.next;
  const MAX_PAGES = 50;
  let guard = 0;
  while (next && guard < MAX_PAGES) {
    const page = await fetchNextPage<T>(next);
    results = results.concat(page.results);
    next = page.next;
    guard += 1;
  }
  if (next) {
    throw new Error(
      `Too many pages for ${path} (cap ${MAX_PAGES}). Use server search or paginated list.`,
    );
  }
  return results;
}
