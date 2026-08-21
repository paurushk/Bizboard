import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Divider from '@mui/material/Divider';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link as RouterLink, useLocation, useParams } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import {
  cancelPurchase,
  completePurchase,
  getPurchase,
} from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { StatusChip } from '@/components/StatusChip';
import { t } from '@/i18n';
import { formatMoney, toNumber } from '@/utils/money';
import { canCancelDocuments } from '@/utils/permissions';
import { documentStatusTone, statusLabelKey } from '@/utils/status';

export function PurchaseDetailPage() {
  const { user } = useAuth();
  const { id } = useParams();
  const location = useLocation();
  const purchaseId = Number(id);
  const qc = useQueryClient();
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(
    () => (location.state as { paymentWarning?: string } | null)?.paymentWarning ?? null,
  );

  const query = useQuery({
    queryKey: ['purchase-invoice', purchaseId],
    queryFn: () => getPurchase(purchaseId),
    enabled: Number.isFinite(purchaseId),
  });

  const completeMutation = useMutation({
    mutationFn: () => completePurchase(purchaseId),
    onSuccess: () => {
      setMessage('Purchase completed');
      void qc.invalidateQueries({ queryKey: ['purchase-invoice', purchaseId] });
      void qc.invalidateQueries({ queryKey: ['purchases'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const cancelMutation = useMutation({
    mutationFn: () => cancelPurchase(purchaseId),
    onSuccess: () => {
      setMessage('Purchase cancelled');
      void qc.invalidateQueries({ queryKey: ['purchase-invoice', purchaseId] });
      void qc.invalidateQueries({ queryKey: ['purchases'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  if (query.isLoading) return <LoadingState />;
  if (query.isError) {
    return <ErrorState message={getErrorMessage(query.error)} onRetry={() => void query.refetch()} />;
  }
  if (!query.data) return <EmptyState />;

  const inv = query.data;
  const showTax = inv.purchaseType === 'GST';
  const hasRcm =
    inv.isReverseCharge ||
    inv.rcmTaxable != null ||
    inv.rcmCgst != null ||
    inv.rcmSgst != null ||
    inv.rcmIgst != null;

  return (
    <Stack spacing={2}>
      <Stack
        direction={{ xs: 'column', sm: 'row' }}
        justifyContent="space-between"
        alignItems={{ xs: 'stretch', sm: 'flex-start' }}
        spacing={1}
      >
        <Box>
          <Typography variant="h4" sx={{ fontFamily: '"IBM Plex Sans", sans-serif' }}>
            {inv.number?.trim() ? inv.number : `Draft #${inv.id}`}
          </Typography>
          <Stack direction="row" spacing={1} alignItems="center" sx={{ mt: 0.5, flexWrap: 'wrap' }}>
            <StatusChip tone={documentStatusTone(inv.status)} labelKey={statusLabelKey(inv.status)} />
            <Chip size="small" label={inv.purchaseType} variant="outlined" />
            {inv.isReverseCharge ? (
              <Chip size="small" label="Reverse charge (RCM)" color="warning" variant="outlined" />
            ) : null}
            <Typography variant="body2" color="text.secondary">
              {inv.invoiceDate}
            </Typography>
          </Stack>
          <Typography sx={{ mt: 1 }}>{inv.supplierName}</Typography>
        </Box>
        <Button component={RouterLink} to="/purchases/history">
          {t('common.back')}
        </Button>
      </Stack>

      {message ? <Alert severity="success">{message}</Alert> : null}
      {error ? <Alert severity="error">{error}</Alert> : null}

      <Paper
        elevation={0}
        sx={{
          p: 1.5,
          position: 'sticky',
          top: 0,
          zIndex: 2,
          bgcolor: 'background.paper',
          borderBottom: 1,
          borderColor: 'divider',
        }}
      >
        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
          {inv.status === 'DRAFT' || inv.status === 'COMPLETED' ? (
            <Button
              component={RouterLink}
              to={`/purchases/history/${inv.id}/edit`}
              variant="outlined"
            >
              {t('common.edit')}
            </Button>
          ) : null}
          {inv.status === 'DRAFT' ? (
            <Button
              variant="contained"
              disabled={completeMutation.isPending}
              onClick={() => completeMutation.mutate()}
            >
              {t('common.complete')}
            </Button>
          ) : null}
          {inv.status === 'COMPLETED' && canCancelDocuments(user) ? (
            <Button
              color="error"
              variant="outlined"
              disabled={cancelMutation.isPending}
              onClick={() => {
                if (window.confirm(`Cancel purchase ${inv.number ?? inv.id}? This cannot be undone.`)) {
                  cancelMutation.mutate();
                }
              }}
            >
              {t('common.cancel')}
            </Button>
          ) : null}
        </Stack>
      </Paper>

      <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
        <Paper sx={{ p: 2, flex: 1 }}>
          <Typography variant="subtitle2" color="text.secondary">
            {t('billing.paymentSummary')}
          </Typography>
          <Divider sx={{ my: 1 }} />
          <Stack spacing={0.75}>
            <Stack direction="row" justifyContent="space-between">
              <Typography>{t('billing.grandTotal')}</Typography>
              <Typography fontWeight={700}>{formatMoney(inv.grandTotal)}</Typography>
            </Stack>
            <Stack direction="row" justifyContent="space-between">
              <Typography>{t('billing.paid')}</Typography>
              <Typography>{formatMoney(inv.paid ?? 0)}</Typography>
            </Stack>
            <Stack direction="row" justifyContent="space-between">
              <Typography>{t('billing.balance')}</Typography>
              <Typography fontWeight={600}>{formatMoney(inv.balance ?? inv.grandTotal)}</Typography>
            </Stack>
          </Stack>
        </Paper>
        <Paper sx={{ p: 2, flex: 1 }}>
          <Typography variant="subtitle2" color="text.secondary">
            {t('billing.taxTotals')}
          </Typography>
          <Divider sx={{ my: 1 }} />
          <Stack spacing={0.75}>
            <Stack direction="row" justifyContent="space-between">
              <Typography>Taxable</Typography>
              <Typography>{formatMoney(inv.taxableTotal)}</Typography>
            </Stack>
            {showTax ? (
              <>
                <Stack direction="row" justifyContent="space-between">
                  <Typography>CGST</Typography>
                  <Typography>{formatMoney(inv.cgstTotal)}</Typography>
                </Stack>
                <Stack direction="row" justifyContent="space-between">
                  <Typography>SGST</Typography>
                  <Typography>{formatMoney(inv.sgstTotal)}</Typography>
                </Stack>
                <Stack direction="row" justifyContent="space-between">
                  <Typography>IGST</Typography>
                  <Typography>{formatMoney(inv.igstTotal)}</Typography>
                </Stack>
              </>
            ) : null}
            {hasRcm ? (
              <>
                <Divider sx={{ my: 0.5 }} />
                <Typography variant="caption" color="text.secondary">
                  Reverse charge (RCM)
                </Typography>
                {inv.rcmTaxable != null ? (
                  <Stack direction="row" justifyContent="space-between">
                    <Typography>RCM taxable</Typography>
                    <Typography>{formatMoney(inv.rcmTaxable)}</Typography>
                  </Stack>
                ) : null}
                {inv.rcmCgst != null ? (
                  <Stack direction="row" justifyContent="space-between">
                    <Typography>RCM CGST</Typography>
                    <Typography>{formatMoney(inv.rcmCgst)}</Typography>
                  </Stack>
                ) : null}
                {inv.rcmSgst != null ? (
                  <Stack direction="row" justifyContent="space-between">
                    <Typography>RCM SGST</Typography>
                    <Typography>{formatMoney(inv.rcmSgst)}</Typography>
                  </Stack>
                ) : null}
                {inv.rcmIgst != null ? (
                  <Stack direction="row" justifyContent="space-between">
                    <Typography>RCM IGST</Typography>
                    <Typography>{formatMoney(inv.rcmIgst)}</Typography>
                  </Stack>
                ) : null}
              </>
            ) : null}
          </Stack>
        </Paper>
      </Stack>

      <Paper sx={{ overflow: 'auto' }}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>#</TableCell>
              <TableCell>{t('nav.products')}</TableCell>
              <TableCell>HSN</TableCell>
              <TableCell align="right">{t('billing.qty')}</TableCell>
              <TableCell align="right">{t('billing.price')}</TableCell>
              {showTax ? <TableCell align="right">{t('billing.tax')}</TableCell> : null}
              <TableCell align="right">{t('common.total')}</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {(inv.items ?? []).map((item, idx) => {
              const lineTax =
                toNumber(item.cgst) + toNumber(item.sgst) + toNumber(item.igst);
              return (
                <TableRow key={item.id ?? `${item.product}-${item.quantity}`}>
                  <TableCell>{idx + 1}</TableCell>
                  <TableCell>
                    {item.productName ?? item.description ?? item.product}
                  </TableCell>
                  <TableCell>{item.hsnCode || '—'}</TableCell>
                  <TableCell align="right">{toNumber(item.quantity)}</TableCell>
                  <TableCell align="right">{formatMoney(item.unitPrice)}</TableCell>
                  {showTax ? (
                    <TableCell align="right">{formatMoney(lineTax)}</TableCell>
                  ) : null}
                  <TableCell align="right">{formatMoney(item.lineTotal)}</TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </Paper>
    </Stack>
  );
}
