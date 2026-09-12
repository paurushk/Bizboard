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
import { ForbiddenPage } from '@/pages/ForbiddenPage';
import { useAuth } from '@/auth/AuthContext';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';

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
}

const SERIES_DEFINITIONS = [
  { name: 'Sales Invoices', endpoint: 'sales/invoices' },
  { name: 'Quotations', endpoint: 'sales/quotations' },
  { name: 'Sales Orders', endpoint: 'sales/orders' },
  { name: 'Delivery Challans', endpoint: 'sales/delivery-challans' },
  { name: 'Sales Credit Notes', endpoint: 'sales/credit-notes' },
  { name: 'Sales Debit Notes', endpoint: 'sales/debit-notes' },
  { name: 'Purchase Invoices', endpoint: 'purchases/invoices' },
  { name: 'Purchase Orders', endpoint: 'purchases/orders' },
  { name: 'Goods Receipt Notes (GRN)', endpoint: 'purchases/grns' },
  { name: 'Purchase Credit Notes', endpoint: 'purchases/credit-notes' },
  { name: 'Purchase Debit Notes', endpoint: 'purchases/debit-notes' },
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
              name: def.name,
              endpoint: def.endpoint,
            } as DocumentSeriesConfig;
          } catch {
            return {
              docType: def.name,
              name: def.name,
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
    return <LoadingState label="Loading document series configurations..." />;
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
        <Typography variant="h5" fontWeight={600}>
          Document Number Series
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Configure independent, concurrency-safe sequential prefixes, padding, and next numbers for all commercial and statutory documents.
        </Typography>
      </Box>

      {error && <HelpErrorAlert error={error} />}

      <TableContainer component={Paper} variant="outlined">
        <Table>
          <TableHead>
            <TableRow>
              <TableCell>Document Type</TableCell>
              <TableCell>Current Prefix</TableCell>
              <TableCell align="right">Next Number</TableCell>
              <TableCell align="right">Padding</TableCell>
              <TableCell>Next Sample Preview</TableCell>
              <TableCell align="right">Action</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {seriesList.map((row) => (
              <TableRow key={row.endpoint}>
                <TableCell sx={{ fontWeight: 500 }}>{row.name}</TableCell>
                <TableCell sx={{ fontFamily: 'monospace' }}>{row.prefix}</TableCell>
                <TableCell align="right">{row.nextNumber}</TableCell>
                <TableCell align="right">{row.padding}</TableCell>
                <TableCell sx={{ fontFamily: 'monospace', fontWeight: 600 }}>
                  {row.preview || '—'}
                </TableCell>
                <TableCell align="right">
                  <Button size="small" variant="outlined" onClick={() => handleEdit(row)}>
                    Configure
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>

      <Dialog open={!!editing} onClose={() => setEditing(null)} maxWidth="sm" fullWidth>
        <DialogTitle>Configure Series: {editing?.name}</DialogTitle>
        <DialogContent>
          <Stack spacing={2.5} sx={{ mt: 1 }}>
            {error && <HelpErrorAlert error={error} />}
            <TextField
              label="Prefix"
              value={prefix}
              onChange={(e) => setPrefix(e.target.value)}
              helperText="E.g. INV-2026, QTN, DC, or custom identifier"
              fullWidth
            />
            <TextField
              label="Next Number"
              type="number"
              value={nextNumber}
              onChange={(e) => setNextNumber(Math.max(1, parseInt(e.target.value) || 1))}
              helperText="The sequence number for the next completed document"
              fullWidth
            />
            <TextField
              label="Minimum Padding Digits"
              type="number"
              value={padding}
              onChange={(e) => setPadding(Math.max(1, Math.min(10, parseInt(e.target.value) || 1)))}
              helperText="Leading zeros (e.g. 5 digits → 00001)"
              fullWidth
            />
            <Paper variant="outlined" sx={{ p: 2, bgcolor: 'action.hover' }}>
              <Typography variant="caption" color="text.secondary" display="block">
                Sample Output Preview:
              </Typography>
              <Typography variant="h6" sx={{ fontFamily: 'monospace', mt: 0.5 }}>
                {calculatePreview()}
              </Typography>
            </Paper>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEditing(null)}>Cancel</Button>
          <Button
            variant="contained"
            onClick={() => saveMutation.mutate()}
            disabled={saveMutation.isPending}
          >
            {saveMutation.isPending ? 'Saving...' : 'Save Configuration'}
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}
