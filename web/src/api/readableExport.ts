/** WP-DL1: the readable (CSV + PDF) export an owner can open without Bizboard. */
import { apiClient, unwrapData } from './client';
import { getBlob } from './legacy/common';

export interface ReadableExport {
  id: number;
  status: 'PENDING' | 'READY' | 'FAILED' | 'EXPIRED';
  size: number;
  createdAt: string;
  readyAt: string | null;
  expiresAt: string | null;
  error: string;
  formatVersion: string;
}

export async function listReadableExports(): Promise<ReadableExport[]> {
  const { data } = await apiClient.get('/company/export/readable/');
  const body = unwrapData<ReadableExport[]>(data);
  return Array.isArray(body) ? body : [];
}

export async function requestReadableExport(input: { password: string; code?: string }): Promise<ReadableExport> {
  const { data } = await apiClient.post('/company/export/readable/', { password: input.password, code: input.code ?? '' });
  return unwrapData(data);
}

/** Fetched with the auth header (not a bare link) and saved as a file. */
export async function downloadReadableExport(id: number): Promise<void> {
  // getBlob turns a refused download (410 expired) back into the JSON error the panel shows.
  const blob = await getBlob(`/company/export/readable/${id}/file/`);
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `bizboard-data-${id}.zip`;
  a.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
}
