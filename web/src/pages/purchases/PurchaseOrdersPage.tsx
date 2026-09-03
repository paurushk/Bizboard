import { useState } from 'react';
import Button from '@mui/material/Button';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import { cancelPurchaseOrder, convertPurchaseOrder, listPurchaseOrdersPage } from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { DocumentListPage } from '@/components/DocumentListPage';
import { t } from '@/i18n';
import { canCancelDocuments, canCreatePurchases } from '@/utils/permissions';

const PAGE_SIZE = 50;

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
  const query = useQuery({
    queryKey: ['purchase-orders', page],
    queryFn: () => listPurchaseOrdersPage({ page, pageSize: PAGE_SIZE }),
  });

  const convertMutation = useMutation({
    mutationFn: (id: number) => convertPurchaseOrder(id),
    onSuccess: () => {
      setConvertingId(null);
      setError(null);
      void qc.invalidateQueries({ queryKey: ['purchase-orders'] });
      void navigate('/purchases/history');
    },
    onError: (err) => {
      setConvertingId(null);
      setError(getErrorMessage(err));
    },
  });

  const cancel = useMutation({
    mutationFn: (id: number) => cancelPurchaseOrder(id),
    onSuccess: () => {
      setConfirmCancelId(null);
      setError(null);
      void qc.invalidateQueries({ queryKey: ['purchase-orders'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  return (
    <>
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
                onClick={() => {
                  setConvertingId(row.id);
                  convertMutation.mutate(row.id);
                }}
              >
                {t('common.convert')}
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
        open={confirmCancelId !== null}
        title={t('common.confirm')}
        body={t('history.confirmCancelPurchaseOrder')}
        confirmLabel={t('history.confirmCancelAction')}
        confirmColor="error"
        confirming={cancel.isPending}
        onClose={() => setConfirmCancelId(null)}
        onConfirm={() => confirmCancelId && cancel.mutate(confirmCancelId)}
      />
    </>
  );
}
