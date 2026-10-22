import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation } from '@tanstack/react-query';
import { commitLegacyImport, uploadLegacyImport, type LegacySource } from '@/api/legacyImport';
import { isRuntimeFlagEnabled } from '@/config/featureFlags';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import { t } from '@/i18n';

const SOURCES: LegacySource[] = ['busy', 'vyapar', 'marg'];

/**
 * WP-GR1b: one-time import of parties and items from Busy, Vyapar or Marg — upload, check the
 * counts, confirm. Shown only when support has switched it on for this company.
 */
export function LegacyImportPanel() {
  const [source, setSource] = useState<LegacySource>('busy');
  const [file, setFile] = useState<File | null>(null);
  const upload = useMutation({ mutationFn: () => uploadLegacyImport(source, file as File) });
  const commit = useMutation({ mutationFn: (id: number) => commitLegacyImport(id) });
  if (!isRuntimeFlagEnabled('ENABLE_LEGACY_IMPORT')) return null;
  const preview = upload.data;
  const errors = preview?.errors ?? [];
  return (
    <Paper sx={{ p: 3 }}>
      <Stack spacing={1.5}>
        <Typography variant="h6">{t('legacyImport.title')}</Typography>
        <Typography variant="body2" color="text.secondary">
          {t('legacyImport.help')}
        </Typography>
        <TextField
          select
          label={t('legacyImport.source')}
          value={source}
          onChange={(e) => setSource(e.target.value as LegacySource)}
          sx={{ maxWidth: 280 }}
        >
          {SOURCES.map((s) => (
            <MenuItem key={s} value={s}>
              {t(`legacyImport.sources.${s}`)}
            </MenuItem>
          ))}
        </TextField>
        <Button variant="outlined" component="label" sx={{ alignSelf: 'flex-start' }}>
          {file ? file.name : t('legacyImport.chooseFile')}
          <input
            hidden
            type="file"
            accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
        </Button>
        <Button variant="contained" sx={{ alignSelf: 'flex-start' }} disabled={!file || upload.isPending} onClick={() => upload.mutate()}>
          {t('legacyImport.check')}
        </Button>
        {upload.isError ? <HelpErrorAlert error={upload.error} /> : null}
        {preview ? (
          <Alert severity={errors.length ? 'warning' : 'info'}>
            {t('legacyImport.counts', {
              customers: String(preview.preview.counts?.customers ?? 0),
              suppliers: String(preview.preview.counts?.suppliers ?? 0),
              products: String(preview.preview.counts?.products ?? 0),
            })}
            {errors.map((e) => (
              <div key={`${e.row}-${e.error}`}>{t('legacyImport.rowError', { row: String(e.row), error: e.error })}</div>
            ))}
          </Alert>
        ) : null}
        {preview && !errors.length ? (
          <Button
            variant="contained"
            color="success"
            sx={{ alignSelf: 'flex-start' }}
            disabled={commit.isPending || commit.isSuccess}
            onClick={() => commit.mutate(preview.syncRunId)}
          >
            {t('legacyImport.confirm')}
          </Button>
        ) : null}
        {commit.isError ? <HelpErrorAlert error={commit.error} /> : null}
        {commit.isSuccess ? <Alert severity="success">{t('legacyImport.done')}</Alert> : null}
      </Stack>
    </Paper>
  );
}
