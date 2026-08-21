import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { downloadTcsWorksheet, downloadTdsWorksheet } from '@/api/resources';
import { PageShell } from '@/pages/phase/phaseShared';

export function TdsTcsReportsPage() {
  const [period, setPeriod] = useState(() => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
  });
  const [error, setError] = useState('');
  const download = async (kind: 'tds' | 'tcs') => {
    setError('');
    try {
      const blob = kind === 'tds' ? await downloadTdsWorksheet(period) : await downloadTcsWorksheet(period);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = kind === 'tds' ? `tds-26q-${period}.csv` : `tcs-27eq-${period}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Download failed');
    }
  };
  return (
    <PageShell title="TDS / TCS worksheets" subtitle="26Q / 27EQ filing aids — not live Income-tax portal upload.">
      <Alert severity="info">
        These CSVs help prepare Form 26Q (TDS) and 27EQ (TCS). BizBoard does not upload to the IT portal.
      </Alert>
      {error ? <Alert severity="error">{error}</Alert> : null}
      <Paper variant="outlined" sx={{ p: 2, mt: 2 }}>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} alignItems="center">
          <TextField size="small" label="Period (YYYY-MM)" value={period} onChange={(e) => setPeriod(e.target.value)} />
          <Button variant="contained" onClick={() => void download('tds')}>Download 26Q TDS aid</Button>
          <Button variant="outlined" onClick={() => void download('tcs')}>Download 27EQ TCS aid</Button>
        </Stack>
        <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
          Owner only. Requires ENABLE_TDS.
        </Typography>
      </Paper>
    </PageShell>
  );
}
