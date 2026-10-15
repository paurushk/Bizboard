import { useState } from 'react';
import Button from '@mui/material/Button';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import Alert from '@mui/material/Alert';
import { getErrorMessage } from '@/api/client';
import { cancelPurchaseOrder, convertPurchaseOrder, listPurchaseOrdersPage } from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { DocumentListPage } from '@/components/DocumentListPage';
import { t } from '@/i18n';
import { invalidatePurchaseSideEffects } from '@/pages/purchases/purchaseQueries';
import { canCancelDocuments, canCreatePurchases } from '@/utils/permissions';

const PAGE_SIZE = 50;

function orderLabel(rows: Array<{ id: number; number?: string | null }> | undefined, id: number | null): string {
  const row = rows?.find((r) => r.id === id);
  return row?.number?.trim() ? row.number : id !== null ? `#${id}` : '';
}

export function PurchaseOrdersPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const canWrite = canCreatePurchases(user);
  const canCancel = canCancelDocuments(user);
  const [page, setPage] = useState(1);
  const [convertingId, setConvertingId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmCancelId, setConfirmCancelId] = useState<number | null>(null);
  const [confirmConvertId, setConfirmConvertId] = useState<number | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const query = useQuery({
    queryKey: ['purchase-orders', page],
    queryFn: () => listPurchaseOrdersPage({ page, pageSize: PAGE_SIZE }),
  });

  const convertMutation = useMutation({
    mutationFn: (id: number) => convertPurchaseOrder(id),
    onSuccess: (invoice) => {
      setConvertingId(null);
      setConfirmConvertId(null);
      setError(null);
      void qc.invalidateQueries({ queryKey: ['purchase-orders'] });
      invalidatePurchaseSideEffects(qc, { invoiceId: invoice.id });
      // Land on the bill that was just created, not on a list it has to be found in.
      void navigate(`/purchases/history/${invoice.id}`, {
        state: {
          message: t('poActions.converted', { label: invoice.number?.trim() ? invoice.number : `#${invoice.id}` }),
        },
      });
    },
    onError: (err) => {
      setConvertingId(null);
      setConfirmConvertId(null);
      setError(getErrorMessage(err));
    },
  });

  const cancel = useMutation({
    mutationFn: (id: number) => cancelPurchaseOrder(id),
    onSuccess: (order) => {
      setConfirmCancelId(null);
      setError(null);
      setMessage(t('poActions.cancelled', { label: order.number?.trim() ? order.number : `#${order.id}` }));
      void qc.invalidateQueries({ queryKey: ['purchase-orders'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  return (
    <>
      {message ? (
        <Alert severity="success" onClose={() => setMessage(null)} sx={{ mb: 1 }}>
          {message}
        </Alert>
      ) : null}
      <DocumentListPage
        titleKey="nav.purchaseOrders"
        newPath="/purchases/orders/new"
        createLabelKey="phase1.newPurchaseOrder"
        detailPath={(id) => `/purchases/orders/${id}`}
        partyLabelKey="billing.supplier"
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
        rows={query.data?.results.map((o) => ({
          id: o.id,
          number: o.number,
          date: o.orderDate,
          partyName: o.supplierName,
          status: o.status,
          grandTotal: o.grandTotal,
        }))}
        extraColumn={(row) => {
          if (row.status === 'DRAFT' && canWrite) {
            return (
              <Button
                size="small"
                disabled={convertMutation.isPending && convertingId === row.id}
                onClick={() => setConfirmConvertId(row.id)}
              >
                {t('poActions.convert')}
              </Button>
            );
          }
          if (row.status === 'COMPLETED' && canCancel) {
            return (
              <Button size="small" color="warning" onClick={() => setConfirmCancelId(row.id)}>
                {t('common.cancel')}
              </Button>
            );
          }
          return null;
        }}
      />
      <ConfirmDialog
        open={confirmConvertId !== null}
        title={t('common.confirm')}
        body={t('poActions.confirmConvert', { label: orderLabel(query.data?.results, confirmConvertId) })}
        confirmLabel={t('poActions.convert')}
        confirming={convertMutation.isPending}
        onClose={() => setConfirmConvertId(null)}
        onConfirm={() => {
          if (confirmConvertId === null) return;
          setConvertingId(confirmConvertId);
          convertMutation.mutate(confirmConvertId);
        }}
      />
      <ConfirmDialog
        open={confirmCancelId !== null}
        title={t('common.confirm')}
        body={t('poActions.confirmCancel', { label: orderLabel(query.data?.results, confirmCancelId) })}
        confirmLabel={t('history.confirmCancelAction')}
        confirmColor="error"
        confirming={cancel.isPending}
        onClose={() => setConfirmCancelId(null)}
        onConfirm={() => confirmCancelId && cancel.mutate(confirmCancelId)}
      />
    </>
  );
}
