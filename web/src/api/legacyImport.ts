/** WP-GR1b: one-time import from Busy, Vyapar or Marg (same preview and commit as Tally). */
import { apiClient, unwrapData } from './client';

export type LegacySource = 'busy' | 'vyapar' | 'marg';

export interface LegacyUploadResult {
  syncRunId: number;
  status: string;
  preview: { counts?: { customers?: number; suppliers?: number; products?: number; errors?: number } };
  errors: Array<{ row: number; error: string }>;
}

export async function uploadLegacyImport(source: LegacySource, file: File): Promise<LegacyUploadResult> {
  const form = new FormData();
  form.append('source', source);
  form.append('file', file);
  const { data } = await apiClient.post('/integrations/legacy/upload/', form);
  return unwrapData(data);
}

export async function commitLegacyImport(syncRunId: number): Promise<unknown> {
  const { data } = await apiClient.post('/integrations/legacy/commit/', { sync_run_id: syncRunId });
  return unwrapData(data);
}
