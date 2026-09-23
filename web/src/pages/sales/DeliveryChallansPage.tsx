import { useState } from 'react';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import {
  cancelDeliveryChallan,
  completeDeliveryChallan,
  completeDeliveryChallanReturn,
  convertDeliveryChallan,
  createDeliveryChallanReturn,
  downloadSalesDocumentPdf,
  getDeliveryChallan,
  listDeliveryChallansPage,
} from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { todayIso } from '@/components/billing';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { DocumentListPage } from '@/components/DocumentListPage';
import { printBlob } from '@/utils/blob';
import { t } from '@/i18n';
import { toNumber } from '@/utils/money';
import { canCancelDocuments, canCreateSales } from '@/utils/permissions';

const PAGE_SIZE = 50;

export function DeliveryChallansPage() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const canWrite = canCreateSales(user);
  const canCancel = canCancelDocuments(user);
  const [page, setPage] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const [confirmCancelId, setConfirmCancelId] = useState<number | null>(null);
  const [returnId, setReturnId] = useState<number | null>(null);
  const [returnQtys, setReturnQtys] = useState<Record<number, string>>({});
  const query = useQuery({
    queryKey: ['delivery-challans', page],
    queryFn: () => listDeliveryChallansPage({ page, pageSize: PAGE_SIZE }),
  });
  const challanForReturn = useQuery({
    queryKey: ['delivery-challan', returnId],
    queryFn: () => getDeliveryChallan(returnId as number),
    enabled: Boolean(returnId),
  });

  const returnMutation = useMutation({
    mutationFn: async () => {
      const challan = challanForReturn.data;
      if (!challan) throw new Error('Challan not loaded');
      const items = (challan.items ?? [])
        .map((item) => ({
          product: item.product,
          quantity: toNumber(returnQtys[item.id ?? 0] ?? item.quantity),
          unitPrice: item.unitPrice,
          gstRate: item.gstRate,
        }))
        .filter((row) => row.quantity > 0);
      if (!items.length) throw new Error(t('phase1.selectInvoiceLines'));
      const created = await createDeliveryChallanReturn({
        challan: challan.id,
        customer: challan.customer,
        returnDate: todayIso(),
        items,
      });
      return completeDeliveryChallanReturn(Number(created.id));
    },
    onSuccess: () => {
      setReturnId(null);
      setReturnQtys({});
      setError(null);
      void qc.invalidateQueries({ queryKey: ['delivery-challans'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });
  const complete = useMutation({
    mutationFn: (id: number) => completeDeliveryChallan(id),
    onSuccess: () => {
      setError(null);
      void qc.invalidateQueries({ queryKey: ['delivery-challans'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });
  const convert = useMutation({
    mutationFn: (id: number) => convertDeliveryChallan(id),
    onSuccess: (invoice) => {
      setError(null);
      void qc.invalidateQueries({ queryKey: ['delivery-challans'] });
      void qc.invalidateQueries({ queryKey: ['sales-invoices'] });
      void navigate(`/sales/history/${invoice.id}/edit`);
    },
    onError: (err) => setError(getErrorMessage(err)),
  });
  const cancel = useMutation({
    mutationFn: (id: number) => cancelDeliveryChallan(id),
    onSuccess: () => {
      setError(null);
      setConfirmCancelId(null);
      void qc.invalidateQueries({ queryKey: ['delivery-challans'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  return (
    <>
      <DocumentListPage
        titleKey="nav.deliveryChallans"
        newPath="/sales/delivery-challans/new"
        createLabelKey="phase1.newDeliveryChallan"
        detailPath={(id) => `/sales/delivery-challans/${id}`}
        partyLabelKey="billing.customer"
        loading={query.isLoading}
        error={error ?? (query.isError ? getErrorMessage(query.error) : null)}
        onRetry={() => void query.refetch()}
        showCreate={canWrite}
        page={page}
        pageSize={PAGE_SIZE}
        count={query.data?.count}
        hasNext={Boolean(query.data?.next)}
        hasPrevious={Boolean(query.data?.previous) || page > 1}
        onPageChange={setPage}
        rows={query.data?.results.map((c) => ({
          id: c.id,
          number: c.number,
          date: c.challanDate,
          partyName: c.customerName,
          status: c.status,
          grandTotal: c.grandTotal,
        }))}
        rowActions={(row) => (
          <>
            {row.status === 'DRAFT' && canWrite ? (
              <Button size="small" disabled={complete.isPending} onClick={() => complete.mutate(row.id)}>
                {t('common.complete')}
              </Button>
            ) : null}
            {row.status === 'COMPLETED' && canWrite ? (
              <Button size="small" variant="outlined" onClick={() => setReturnId(row.id)}>
                {t('phase1.returnChallan')}
              </Button>
            ) : null}
            {row.status === 'COMPLETED' && canWrite ? (
              <Button size="small" variant="contained" disabled={convert.isPending} onClick={() => convert.mutate(row.id)}>
                {t('common.convert')}
              </Button>
            ) : null}
            {row.status === 'COMPLETED' ? (
              <Button
                size="small"
                onClick={() =>
                  void downloadSalesDocumentPdf('delivery-challan', row.id)
                    .then((blob) => printBlob(blob))
                    .catch((err) => setError(getErrorMessage(err)))
                }
              >
                {t('billing.print')}
              </Button>
            ) : null}
            {row.status === 'COMPLETED' && canCancel ? (
              <Button size="small" color="warning" onClick={() => setConfirmCancelId(row.id)}>
                {t('common.cancel')}
              </Button>
            ) : null}
          </>
        )}
      />
      <Dialog open={Boolean(returnId)} onClose={() => setReturnId(null)} fullWidth maxWidth="sm">
        <DialogTitle>{t('phase1.returnChallan')}</DialogTitle>
        <DialogContent>
          <Stack spacing={1} sx={{ mt: 1 }}>
            {(challanForReturn.data?.items ?? []).map((item) => (
              <Stack key={item.id ?? item.product} direction="row" spacing={1} alignItems="center">
                <Typography sx={{ flex: 1 }}>{item.productName ?? item.product}</Typography>
                <TextField
                  size="small"
                  type="number"
                  label={t('billing.qty')}
                  value={returnQtys[item.id ?? 0] ?? String(item.quantity)}
                  onChange={(e) =>
                    setReturnQtys((prev) => ({ ...prev, [item.id ?? 0]: e.target.value }))
                  }
                  inputProps={{ min: 0, max: toNumber(item.quantity), step: 'any' }}
                  sx={{ width: 120 }}
                />
              </Stack>
            ))}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setReturnId(null)}>{t('common.close')}</Button>
          <Button
            variant="contained"
            disabled={returnMutation.isPending || !challanForReturn.data}
            onClick={() => returnMutation.mutate()}
          >
            {t('common.complete')}
          </Button>
        </DialogActions>
      </Dialog>
      <ConfirmDialog
        open={confirmCancelId !== null}
        title={t('common.confirm')}
        body={t('history.confirmCancelDeliveryChallan')}
        confirmLabel={t('history.confirmCancelAction')}
        confirmColor="error"
        confirming={cancel.isPending}
        onClose={() => setConfirmCancelId(null)}
        onConfirm={() => confirmCancelId && cancel.mutate(confirmCancelId)}
      />
    </>
  );
}
