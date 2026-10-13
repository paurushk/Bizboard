import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import List from '@mui/material/List';
import ListItem from '@mui/material/ListItem';
import ListItemText from '@mui/material/ListItemText';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import { cancelImport, listBillImportJobs } from '@/api/resources';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { t } from '@/i18n';
import type { ImportKind } from '@/types/domain';
import { statusLabelKey } from '@/utils/status';

type Props = {
  kind: Extract<ImportKind, 'PURCHASE_BILL' | 'SALES_BILL'>;
  onResume: (jobId: number) => void;
};

/**
 * Unfinished uploads of this kind, so a job left in review or extraction
 * (closed tab, refresh, phone locked) can always be found again.
 */
export function RecentBillUploads({ kind, onResume }: Props) {
  const queryClient = useQueryClient();
  const jobs = useQuery({
    queryKey: ['recent-bill-uploads', kind],
    queryFn: () => listBillImportJobs(kind),
  });
  const [pendingDiscard, setPendingDiscard] = useState<number | null>(null);
  const [discardError, setDiscardError] = useState<string | null>(null);
  const discard = useMutation({
    mutationFn: (id: number) => cancelImport(id),
    onSuccess: () => {
      setPendingDiscard(null);
      setDiscardError(null);
      void queryClient.invalidateQueries({ queryKey: ['recent-bill-uploads', kind] });
    },
    onError: (err) => {
      setPendingDiscard(null);
      setDiscardError(getErrorMessage(err));
    },
  });
  const rows = (jobs.data ?? []).slice(0, 10);
  if (rows.length === 0) return null;
  return (
    <Paper sx={{ p: 2 }}>
      <Typography variant="subtitle1" gutterBottom>
        {t('billUpload.recentTitle')}
      </Typography>
      {discardError ? (
        <Alert severity="error" sx={{ mb: 1 }} onClose={() => setDiscardError(null)}>
          {discardError}
        </Alert>
      ) : null}
      <ConfirmDialog
        open={pendingDiscard != null}
        title={t('billUpload.discardTitle')}
        body={t('billUpload.discardBody')}
        confirmLabel={t('billUpload.recentDiscard')}
        confirmColor="error"
        confirming={discard.isPending}
        onConfirm={() => pendingDiscard != null && discard.mutate(pendingDiscard)}
        onClose={() => setPendingDiscard(null)}
      />
      <List dense disablePadding>
        {rows.map((job) => (
          <ListItem
            key={job.id}
            disableGutters
            secondaryAction={
              <Stack direction="row" spacing={1}>
                <Button size="small" onClick={() => onResume(job.id)}>
                  {t('billUpload.recentResume')}
                </Button>
                <Button
                  size="small"
                  color="inherit"
                  disabled={discard.isPending}
                  onClick={() => setPendingDiscard(job.id)}
                >
                  {t('billUpload.recentDiscard')}
                </Button>
              </Stack>
            }
          >
            <ListItemText
              primary={t('billUpload.recentAge', {
                name: job.fileName || `#${job.id}`,
                status: t(statusLabelKey(job.status)),
              })}
              secondary={job.createdAt ? new Date(job.createdAt).toLocaleString() : undefined}
            />
          </ListItem>
        ))}
      </List>
    </Paper>
  );
}
