import { useState } from 'react';
import { getErrorMessage } from '@/api/client';
import { downloadAccountingReport } from '@/api/resources';

/** One Excel download for the statements, with the failure kept for the page to show. */
export function useStatementDownload(report: 'trial-balance' | 'profit-and-loss' | 'balance-sheet') {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const run = async (params: Record<string, string>) => {
    setBusy(true);
    setError(null);
    try {
      const { url } = await downloadAccountingReport(report, params);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${report}.xlsx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 10_000);
    } catch (e) {
      setError(getErrorMessage(e));
    } finally {
      setBusy(false);
    }
  };
  return { busy, error, run };
}
