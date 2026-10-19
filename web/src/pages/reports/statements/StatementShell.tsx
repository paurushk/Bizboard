import { type ReactNode } from 'react';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import LinearProgress from '@mui/material/LinearProgress';
import Stack from '@mui/material/Stack';
import { getErrorMessage } from '@/api/client';
import { ErrorState, LoadingState } from '@/components/PageState';
import { dateRangeForPreset } from '@/components/HistoryFilterBar';
import { t } from '@/i18n';
import { PageShell } from '@/pages/phase/phaseShared';

export type StatementQuery = {
  isLoading: boolean;
  isFetching: boolean;
  isError: boolean;
  error: unknown;
  data?: unknown;
  refetch: () => unknown;
};

const PRESETS = ['thisMonth', 'currentFY', 'previousFY', 'q1', 'q2', 'q3', 'q4'] as const;

export function PresetChips({ onPick }: { onPick: (range: { dateFrom: string; dateTo: string }) => void }) {
  return (
    <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
      {PRESETS.map((p) => (
        <Chip key={p} size="small" label={t(`history.preset.${p}`)} onClick={() => onPick(dateRangeForPreset(p))} />
      ))}
    </Stack>
  );
}

export function DownloadButton({ busy, onClick }: { busy: boolean; onClick: () => void }) {
  return (
    <Button size="small" variant="outlined" disabled={busy} onClick={onClick}>
      {t('statements.download')}
    </Button>
  );
}

/** Keeps the controls on screen while a new range loads and when it fails (RPT-05). */
export function StatementShell({
  title,
  controls,
  query,
  children,
}: {
  title: string;
  controls: ReactNode;
  query: StatementQuery;
  children: ReactNode;
}) {
  const failed = query.isError;
  return (
    <PageShell title={title} actions={controls}>
      {query.isFetching ? <LinearProgress aria-label={t('common.loading')} /> : null}
      {query.isLoading ? <LoadingState /> : null}
      {failed ? (
        <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />
      ) : null}
      {query.data && !failed ? children : null}
    </PageShell>
  );
}
