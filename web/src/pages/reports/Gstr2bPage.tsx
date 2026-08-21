import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import {
  listGstr2bPage,
  matchGstr2b,
  patchGstr2bEligibility,
  type ItcEligibility,
} from '@/api/gstr2b';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { VirtualizedTable } from '@/components/VirtualizedTable';
import { t } from '@/i18n';
import { formatMoney } from '@/utils/money';

function currentPeriod(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
}

export function Gstr2bPage() {
  const qc = useQueryClient();
  const [period, setPeriod] = useState(currentPeriod());
  const [error, setError] = useState<string | null>(null);

  const query = useQuery({
    queryKey: ['gstr2b', period],
    queryFn: () => listGstr2bPage({ period, page: 1, pageSize: 50 }),
  });

  const matchMutation = useMutation({
    mutationFn: () => matchGstr2b(period),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['gstr2b'] }),
    onError: (err) => setError(getErrorMessage(err)),
  });

  const patchMutation = useMutation({
    mutationFn: ({ id, itcEligibility }: { id: number; itcEligibility: ItcEligibility }) =>
      patchGstr2bEligibility(id, itcEligibility),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['gstr2b'] }),
    onError: (err) => setError(getErrorMessage(err)),
  });

  const rows = query.data?.results ?? [];

  return (
    <Stack spacing={2}>
      <Typography variant="h4">{t('nav.gstr2b')}</Typography>
      <Alert severity="info">
        Matched 2B rows marked Ineligible or Reversed are excluded from GSTR-3B claimable ITC.
      </Alert>
      {error ? <Alert severity="error">{error}</Alert> : null}
      <Stack direction="row" spacing={2} alignItems="center">
        <TextField
          label="Period"
          value={period}
          onChange={(e) => setPeriod(e.target.value)}
          size="small"
          sx={{ width: 140 }}
        />
        <Button variant="outlined" onClick={() => matchMutation.mutate()} disabled={matchMutation.isPending}>
          Match purchases
        </Button>
      </Stack>
      {query.isLoading ? <LoadingState /> : null}
      {query.isError ? (
        <ErrorState message={getErrorMessage(query.error)} onRetry={() => void query.refetch()} />
      ) : null}
      {!query.isLoading && rows.length === 0 ? <EmptyState /> : null}
      {rows.length > 0 ? (
        <Paper sx={{ overflow: 'auto' }}>
          <VirtualizedTable rowCount={rows.length} rowHeight={56}>
            {(virtualRows) => (
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Supplier GSTIN</TableCell>
                <TableCell>Invoice</TableCell>
                <TableCell align="right">Taxable</TableCell>
                <TableCell>Match</TableCell>
                <TableCell>{t('billing.itcEligibility')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {/* Companion fix to UXW2B-007 — see SalesHistoryPage for the full explanation:
                  without these spacer rows, scrolling past the first screenful showed blank
                  space instead of the (correctly computed) later rows. */}
              {virtualRows.length > 0 ? (
                <TableRow style={{ height: virtualRows[0].start, padding: 0, border: 0 }} aria-hidden>
                  <TableCell style={{ padding: 0, border: 0 }} colSpan={5} />
                </TableRow>
              ) : null}
              {virtualRows.map((vRow) => {
                const row = rows[vRow.index];
                if (!row) return null;
                return (
                <TableRow key={row.id} style={{ height: vRow.size }}>
                  <TableCell>{row.supplierGstin}</TableCell>
                  <TableCell>{row.invoiceNumber}</TableCell>
                  <TableCell align="right">{formatMoney(row.taxableValue)}</TableCell>
                  <TableCell>{row.matchStatus}</TableCell>
                  <TableCell>
                    <TextField
                      select
                      size="small"
                      value={row.itcEligibility}
                      onChange={(e) =>
                        patchMutation.mutate({
                          id: row.id,
                          itcEligibility: e.target.value as ItcEligibility,
                        })
                      }
                      sx={{ minWidth: 140 }}
                    >
                      <MenuItem value="UNREVIEWED">Unreviewed</MenuItem>
                      <MenuItem value="CLAIMABLE" disabled={row.matchStatus !== 'MATCHED'}>
                        Claimable
                      </MenuItem>
                      <MenuItem value="INELIGIBLE">Ineligible</MenuItem>
                      <MenuItem value="REVERSED">Reversed</MenuItem>
                    </TextField>
                  </TableCell>
                </TableRow>
                );
              })}
              {virtualRows.length > 0 ? (
                <TableRow
                  style={{
                    height: Math.max(0, rows.length * 56 - virtualRows[virtualRows.length - 1].end),
                    padding: 0,
                    border: 0,
                  }}
                  aria-hidden
                >
                  <TableCell style={{ padding: 0, border: 0 }} colSpan={5} />
                </TableRow>
              ) : null}
            </TableBody>
          </Table>
            )}
          </VirtualizedTable>
        </Paper>
      ) : null}
    </Stack>
  );
}
