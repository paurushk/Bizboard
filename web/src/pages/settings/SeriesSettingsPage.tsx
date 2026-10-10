import { useState } from 'react';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableContainer from '@mui/material/TableContainer';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient, getErrorMessage } from '@/api/client';
import { LoadingState, ErrorState } from '@/components/PageState';
import { PageTitle } from '@/contextHelp';
import { ForbiddenPage } from '@/pages/ForbiddenPage';
import { useAuth } from '@/auth/AuthContext';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import { t } from '@/i18n';

interface DocumentSeriesConfig {
  docType: string;
  name: string;
  endpoint: string;
  prefix: string;
  nextNumber: number;
  padding: number;
  gstinKey?: string;
  fyLabel?: string;
  preview?: string;
  nameKey: string;
}

const SERIES_DEFINITIONS = [
  { nameKey: 'cog.seriesSales', endpoint: 'sales/invoices' },
  { nameKey: 'cog.seriesQuotes', endpoint: 'sales/quotations' },
  { nameKey: 'cog.seriesOrders', endpoint: 'sales/orders' },
  { nameKey: 'cog.seriesChallans', endpoint: 'sales/delivery-challans' },
  { nameKey: 'cog.seriesCredit', endpoint: 'sales/credit-notes' },
  { nameKey: 'cog.seriesDebit', endpoint: 'sales/debit-notes' },
  { nameKey: 'cog.seriesPurchases', endpoint: 'purchases/invoices' },
  { nameKey: 'cog.seriesPo', endpoint: 'purchases/orders' },
  { nameKey: 'cog.seriesGrn', endpoint: 'purchases/grns' },
  { nameKey: 'cog.seriesPcn', endpoint: 'purchases/credit-notes' },
  { nameKey: 'cog.seriesPdn', endpoint: 'purchases/debit-notes' },
];

export function SeriesSettingsPage() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const [editing, setEditing] = useState<DocumentSeriesConfig | null>(null);
  const [prefix, setPrefix] = useState('');
  const [nextNumber, setNextNumber] = useState(1);
  const [padding, setPadding] = useState(5);
  const [error, setError] = useState<string | null>(null);

  const isOwner = user?.role === 'OWNER';

  const query = useQuery({
    queryKey: ['document-series-all'],
    queryFn: async () => {
      const results = await Promise.all(
        SERIES_DEFINITIONS.map(async (def) => {
          try {
            const res = await apiClient.get(`${def.endpoint}/number-series/`);
            const d = res.data?.data || res.data;
            return {
              ...d,
              name: def.nameKey,
              nameKey: def.nameKey,
              endpoint: def.endpoint,
            } as DocumentSeriesConfig;
          } catch {
            return {
              docType: def.nameKey,
              name: def.nameKey,
              nameKey: def.nameKey,
              endpoint: def.endpoint,
              prefix: '—',
              nextNumber: 1,
              padding: 5,
              preview: '—',
            } as DocumentSeriesConfig;
          }
        })
      );
      return results;
    },
    enabled: !!user,
  });

  const saveMutation = useMutation({
    mutationFn: async () => {
      if (!editing) return;
      await apiClient.patch(`${editing.endpoint}/number-series/`, {
        prefix,
        next_number: nextNumber,
        padding,
      });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['document-series-all'] });
      setEditing(null);
      setError(null);
    },
    onError: (err) => {
      setError(getErrorMessage(err));
    },
  });

  if (!isOwner) {
    return <ForbiddenPage />;
  }

  if (query.isLoading) {
    return <LoadingState label={t('sweep.loadingSeries')} />;
  }

  if (query.isError) {
    return <ErrorState message={getErrorMessage(query.error)} onRetry={() => query.refetch()} />;
  }

  const seriesList = query.data || [];

  const handleEdit = (item: DocumentSeriesConfig) => {
    setEditing(item);
    setPrefix(item.prefix || '');
    setNextNumber(item.nextNumber || 1);
    setPadding(item.padding || 5);
    setError(null);
  };

  const calculatePreview = () => {
    const numStr = String(nextNumber).padStart(padding, '0');
    return prefix ? `${prefix}-${numStr}` : numStr;
  };

  return (
    <Stack spacing={3}>
      <Box>
        <PageTitle variant="h5" sx={{ fontWeight: 600 }}>
          {t('sweep2.docNumberSeries')}
        </PageTitle>
        <Typography variant="body2" color="text.secondary">
          Configure independent, concurrency-safe sequential prefixes, padding, and next numbers for all commercial and statutory documents.
        </Typography>
        <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.5 }}>
          {t('phase1.quotationNumberGapNote')}
        </Typography>
      </Box>

      {error && <HelpErrorAlert error={error} />}

      <TableContainer component={Paper} variant="outlined">
        <Table>
          <TableHead>
            <TableRow>
              <TableCell>{t('sweep2.docType')}</TableCell>
              <TableCell>{t('sweep2.currentPrefix')}</TableCell>
              <TableCell align="right">{t('sweep2.nextNumber')}</TableCell>
              <TableCell align="right">{t('sweep2.padding')}</TableCell>
              <TableCell>{t('sweep2.nextSamplePreview')}</TableCell>
              <TableCell align="right">{t('sweep2.action')}</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {seriesList.map((row) => (
              <TableRow key={row.endpoint}>
                <TableCell sx={{ fontWeight: 500 }}>{t(row.nameKey)}</TableCell>
                <TableCell sx={{ fontFamily: 'monospace' }}>{row.prefix}</TableCell>
                <TableCell align="right">{row.nextNumber}</TableCell>
                <TableCell align="right">{row.padding}</TableCell>
                <TableCell sx={{ fontFamily: 'monospace', fontWeight: 600 }}>
                  {row.preview || '—'}
                </TableCell>
                <TableCell align="right">
                  <Button size="small" variant="outlined" onClick={() => handleEdit(row)}>
                    {t('sweep2.configure')}
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>

      <Dialog open={!!editing} onClose={() => setEditing(null)} maxWidth="sm" fullWidth>
        <DialogTitle>{editing ? t('cog.configureSeries', { name: t(editing.nameKey) }) : ''}</DialogTitle>
        <DialogContent>
          <Stack spacing={2.5} sx={{ mt: 1 }}>
            {error && <HelpErrorAlert error={error} />}
            <TextField
              label={t('sweep.prefix')}
              value={prefix}
              onChange={(e) => setPrefix(e.target.value)}
              helperText={t('sweep.prefixHelp')}
              fullWidth
            />
            <TextField
              label={t('sweep.nextNumber')}
              type="number"
              value={nextNumber}
              onChange={(e) => setNextNumber(Math.max(1, parseInt(e.target.value) || 1))}
              helperText={t('sweep.nextNumberHelp')}
              fullWidth
            />
            <TextField
              label={t('sweep.minPadding')}
              type="number"
              value={padding}
              onChange={(e) => setPadding(Math.max(1, Math.min(10, parseInt(e.target.value) || 1)))}
              helperText={t('sweep.paddingHelp')}
              fullWidth
            />
            <Paper variant="outlined" sx={{ p: 2, bgcolor: 'action.hover' }}>
              <Typography variant="caption" color="text.secondary" display="block">
                {t('sweep2.sampleOutputPreview')}
              </Typography>
              <Typography variant="h6" sx={{ fontFamily: 'monospace', mt: 0.5 }}>
                {calculatePreview()}
              </Typography>
            </Paper>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEditing(null)}>{t('sweep2.cancel')}</Button>
          <Button
            variant="contained"
            onClick={() => saveMutation.mutate()}
            disabled={saveMutation.isPending}
          >
            {saveMutation.isPending ? t('cog.savingConfig') : t('cog.saveConfiguration')}
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}
