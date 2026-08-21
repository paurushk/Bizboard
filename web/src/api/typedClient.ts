import type { components, paths } from '@/api/openapi-types';

export type ApiPaths = paths;
export type ApiComponents = components;
export type ApiSchemas = components extends { schemas: infer S } ? S : Record<string, never>;

/** Relative path for apiClient (baseURL already includes /api/v1). */
export function apiPath<P extends `/${string}`>(relative: P): P {
  return relative;
}

export function getPath<P extends keyof paths>(path: P): P {
  return path;
}

export type SchemaOr<Name extends string, Fallback> = Name extends keyof ApiSchemas
  ? ApiSchemas[Name]
  : Fallback;

type DataEnvelope<T> = T extends { data: infer D } ? D : T;

export type OpResponse<
  P extends keyof paths,
  M extends 'get' | 'post' | 'put' | 'patch' | 'delete',
> = paths[P] extends { [K in M]?: { responses: { 200?: { content?: { 'application/json'?: infer R } } } } }
  ? DataEnvelope<R>
  : unknown;
