import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { downloadTcsWorksheet, downloadTdsWorksheet } from '@/api/resources';
import { t, useLocale } from '@/i18n';
import { PageShell } from '@/pages/phase/phaseShared';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';

const PERIOD_RE = /^\d{4}-(0[1-9]|1[0-2])$/;

export function TdsTcsReportsPage() {
  useLocale();
  const [period, setPeriod] = useState(() => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
  });
  const [error, setError] = useState('');
  const download = async (kind: 'tds' | 'tcs') => {
    setError('');
    if (!PERIOD_RE.test(period)) {
      setError(t('reports.tdsInvalidPeriod'));
      return;
    }
    try {
      const blob = kind === 'tds' ? await downloadTdsWorksheet(period) : await downloadTcsWorksheet(period);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = kind === 'tds' ? `tds-26q-${period}.csv` : `tcs-27eq-${period}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e instanceof Error ? e.message : t('reports.tdsDownloadFailed'));
    }
  };
  return (
    <PageShell title={t('reports.tdsTitle')} subtitle={t('reports.tdsSubtitle')}>
      <Alert severity="info">{t('reports.tdsInfo')}</Alert>
      {error ? <HelpErrorAlert message={error} /> : null}
      <Paper variant="outlined" sx={{ p: 2, mt: 2 }}>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} alignItems="center">
          <TextField
            size="small"
            type="month"
            label={t('reports.tdsPeriod')}
            value={period}
            onChange={(e) => setPeriod(e.target.value)}
            inputProps={{ pattern: '\\d{4}-\\d{2}' }}
          />
          <Button variant="contained" onClick={() => void download('tds')}>
            {t('reports.tdsDownload26q')}
          </Button>
          <Button variant="outlined" onClick={() => void download('tcs')}>
            {t('reports.tdsDownload27eq')}
          </Button>
        </Stack>
        <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
          {t('reports.tdsOwnerOnly')}
        </Typography>
      </Paper>
    </PageShell>
  );
}
