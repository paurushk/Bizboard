import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { downloadReadableExport, listReadableExports, requestReadableExport } from '@/api/readableExport';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import { t } from '@/i18n';

/**
 * WP-DL1 (owner): "Download my data" as CSV files and invoice PDFs that open in Excel or other
 * software — not only a backup to restore into Bizboard. Prepared in the background; the link
 * works for 24 hours.
 */
export function ReadableExportPanel() {
  const qc = useQueryClient();
  const rows = useQuery({
    queryKey: ['readable-exports'],
    queryFn: listReadableExports,
    refetchInterval: (q) => ((q.state.data ?? []).some((r) => r.status === 'PENDING') ? 15_000 : false),
  });
  const [password, setPassword] = useState('');
  const [code, setCode] = useState('');
  const ask = useMutation({
    mutationFn: () => requestReadableExport({ password, code }),
    onSuccess: () => {
      setPassword('');
      setCode('');
      void qc.invalidateQueries({ queryKey: ['readable-exports'] });
    },
  });
  const save = useMutation({ mutationFn: downloadReadableExport });
  const latest = (rows.data ?? [])[0];
  const [openedAt] = useState(() => Date.now());
  // The daily purge marks a lapsed link EXPIRED; until then a READY row past its time is expired too.
  const expired = latest?.status === 'EXPIRED' || (latest?.status === 'READY' && Boolean(latest.expiresAt)
    && new Date(latest.expiresAt as string).getTime() <= Math.max(openedAt, rows.dataUpdatedAt));

  return (
    <Stack spacing={1.5}>
      <Typography variant="h6">{t('readableExport.title')}</Typography>
      <Typography variant="body2" color="text.secondary">
        {t('readableExport.help')}
      </Typography>
      <TextField
        type="password"
        label={t('readableExport.password')}
        value={password}
        autoComplete="current-password"
        onChange={(e) => setPassword(e.target.value)}
        sx={{ maxWidth: 360 }}
      />
      <TextField label={t('readableExport.code')} value={code} onChange={(e) => setCode(e.target.value)} sx={{ maxWidth: 360 }} />
      {ask.isError ? <HelpErrorAlert error={ask.error} /> : null}
      <Button variant="outlined" sx={{ alignSelf: 'flex-start' }} disabled={!password || ask.isPending} onClick={() => ask.mutate()}>
        {t('readableExport.prepare')}
      </Button>
      {latest?.status === 'PENDING' ? <Alert severity="info">{t('readableExport.pending')}</Alert> : null}
      {latest?.status === 'FAILED' ? <Alert severity="error">{t('readableExport.failed')}</Alert> : null}
      {expired ? <Alert severity="info">{t('readableExport.expired')}</Alert> : null}
      {latest?.status === 'READY' && !expired ? (
        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
          <Button variant="contained" disabled={save.isPending} onClick={() => save.mutate(latest.id)}>
            {t('readableExport.download')}
          </Button>
          <Typography variant="caption" color="text.secondary">
            {t('readableExport.until', { until: latest.expiresAt ? new Date(latest.expiresAt).toLocaleString() : '' })}
          </Typography>
        </Stack>
      ) : null}
      {save.isError ? <HelpErrorAlert error={save.error} /> : null}
    </Stack>
  );
}
