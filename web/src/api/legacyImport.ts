/** WP-GR1b: one-time import from Busy, Vyapar or Marg (same preview and commit as Tally). */
import { apiClient, unwrapData } from './client';

export type LegacySource = 'busy' | 'vyapar' | 'marg';

export interface LegacyUploadResult {
  syncRunId: number;
  status: string;
  preview: {
    counts?: { customers?: number; suppliers?: number; products?: number; errors?: number; skipped?: number };
    /** Rows left out on purpose (bank/expense ledgers, totals) and advances to enter by hand. */
    notes?: Array<{ row: number | null; warning: string }>;
  };
  errors: Array<{ row: number; error: string }>;
}

export async function uploadLegacyImport(source: LegacySource, file: File): Promise<LegacyUploadResult> {
  const form = new FormData();
  form.append('source', source);
  form.append('file', file);
  const { data } = await apiClient.post('/integrations/legacy/upload/', form);
  return unwrapData(data);
}

export interface LegacyCommitResult {
  syncRunId: number;
  result?: { reconciliation?: Record<string, { pass?: boolean } | undefined> };
}

export async function commitLegacyImport(syncRunId: number): Promise<LegacyCommitResult> {
  const { data } = await apiClient.post('/integrations/legacy/commit/', { sync_run_id: syncRunId });
  return unwrapData(data);
}

/** The reconciliation sections (stock, receivables, payables, ...) whose totals did not tie. */
export function failedReconciliation(result: LegacyCommitResult | undefined): string[] {
  const recon = result?.result?.reconciliation ?? {};
  return Object.entries(recon)
    .filter(([, section]) => section && section.pass === false)
    .map(([name]) => name);
}
