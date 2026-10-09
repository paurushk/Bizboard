import { useState } from 'react';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Typography from '@mui/material/Typography';
import Alert from '@mui/material/Alert';
import { useQuery } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import { getInvoiceProfitDetails } from '@/api/resources';
import { t } from '@/i18n';
import { formatMoney, toNumber } from '@/utils/money';

type Props = {
  invoiceId: number | null;
  open: boolean;
  onClose: () => void;
};

export function ProfitDetailsDialog({ invoiceId, open, onClose }: Props) {
  const [showAll, setShowAll] = useState(false);
  const openKey = open ? String(invoiceId ?? '') : '';
  const [seenKey, setSeenKey] = useState(openKey);
  if (seenKey !== openKey) {
    setSeenKey(openKey);
    setShowAll(false);
  }

  const query = useQuery({
    queryKey: ['invoice-profit-details', invoiceId],
    queryFn: () => getInvoiceProfitDetails(invoiceId as number),
    enabled: open && invoiceId != null && invoiceId > 0,
  });

  const data = query.data;
  const lines = data?.lines ?? [];
  const visible = showAll || lines.length <= 4 ? lines : lines.slice(0, 4);
  const profit = toNumber(data?.profit);
  const formula = data?.formula?.trim() || t('invoiceDetail.profitFormula');

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="md">
      <DialogTitle>{t('invoiceDetail.profitCalculation')}</DialogTitle>
      <DialogContent>
        {query.isLoading ? (
          <Typography color="text.secondary">{t('common.loading')}</Typography>
        ) : query.isError ? (
          <Alert severity="error">{getErrorMessage(query.error)}</Alert>
        ) : data ? (
          <Stack spacing={2} sx={{ mt: 1 }}>
            {data.estimated ? <Alert severity="info">{t('invoiceDetail.profitEstimate')}</Alert> : null}
            {data.costIncomplete ? <Alert severity="warning">{t('invoiceDetail.profitCostIncomplete')}</Alert> : null}
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>{t('invoiceDetail.itemName')}</TableCell>
                  <TableCell align="right">{t('common.qty')}</TableCell>
                  <TableCell align="right">{t('invoiceDetail.purchasePriceExcl')}</TableCell>
                  <TableCell align="right">{t('invoiceDetail.totalCost')}</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {visible.map((line, idx) => (
                  <TableRow key={`${line.name}-${idx}`}>
                    <TableCell>
                      {line.name}
                      {line.costMissing ? (
                        <Typography variant="caption" display="block" color="warning.main">
                          {t('invoiceDetail.costMissing')}
                        </Typography>
                      ) : null}
                      {line.fellBackToPurchasePrice ? (
                        <Typography variant="caption" display="block" color="text.secondary">
                          {t('invoiceDetail.fellBackPurchase')}
                        </Typography>
                      ) : null}
                    </TableCell>
                    <TableCell align="right">
                      {toNumber(line.quantity)}
                      {line.unitName ? ` ${line.unitName}` : ''}
                    </TableCell>
                    <TableCell align="right">
                      {line.unitCost == null || line.unitCost === '' ? '—' : formatMoney(line.unitCost)}
                    </TableCell>
                    <TableCell align="right">
                      {line.lineCost == null || line.lineCost === '' ? '—' : formatMoney(line.lineCost)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            {lines.length > 4 && !showAll ? (
              <Button size="small" onClick={() => setShowAll(true)}>
                {t('invoiceDetail.viewAllItems')}
              </Button>
            ) : null}
            <Stack spacing={0.5}>
              <Stack direction="row" justifyContent="space-between">
                <Typography>{t('invoiceDetail.salesAmountExcl')}</Typography>
                <Typography>{formatMoney(data.salesAmount)}</Typography>
              </Stack>
              <Stack direction="row" justifyContent="space-between">
                <Typography>{t('invoiceDetail.totalCost')}</Typography>
                <Typography>{formatMoney(data.totalCost)}</Typography>
              </Stack>
              <Stack direction="row" justifyContent="space-between">
                <Typography>{t('invoiceDetail.gstCollected')}</Typography>
                <Typography>{formatMoney(data.taxPayable)}</Typography>
              </Stack>
              <Stack direction="row" justifyContent="space-between">
                <Typography fontWeight={700}>{t('invoiceDetail.profit')}</Typography>
                <Typography fontWeight={700} color={profit < 0 ? 'error' : 'text.primary'}>
                  {formatMoney(data.profit)}
                </Typography>
              </Stack>
              <Typography variant="body2" color="text.secondary">
                {formula}
              </Typography>
            </Stack>
          </Stack>
        ) : null}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('common.close')}</Button>
      </DialogActions>
    </Dialog>
  );
}
