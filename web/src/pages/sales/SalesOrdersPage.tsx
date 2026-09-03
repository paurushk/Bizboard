import { useState } from 'react';
import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import { cancelSalesOrder, convertSalesOrder, convertSalesOrderToChallan, listSalesOrdersPage } from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { DocumentListPage } from '@/components/DocumentListPage';
import { t } from '@/i18n';
import { canCancelDocuments, canCreateSales } from '@/utils/permissions';

const PAGE_SIZE = 50;

export function SalesOrdersPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const canWrite = canCreateSales(user);
  const canCancel = canCancelDocuments(user);
  const [page, setPage] = useState(1);
  const [convertingId, setConvertingId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmCancelId, setConfirmCancelId] = useState<number | null>(null);
  const query = useQuery({
    queryKey: ['sales-orders', page],
    queryFn: () => listSalesOrdersPage({ page, pageSize: PAGE_SIZE }),
  });

  const convertMutation = useMutation({
    mutationFn: (id: number) => convertSalesOrder(id),
    onSuccess: () => {
      setConvertingId(null);
      setError(null);
      void qc.invalidateQueries({ queryKey: ['sales-orders'] });
      void navigate('/sales/history');
    },
    onError: (err) => {
      setConvertingId(null);
      setError(getErrorMessage(err));
    },
  });

  const convertToChallanMutation = useMutation({
    mutationFn: (id: number) => convertSalesOrderToChallan(id),
    onSuccess: () => {
      setConvertingId(null);
      setError(null);
      void qc.invalidateQueries({ queryKey: ['sales-orders'] });
      void qc.invalidateQueries({ queryKey: ['delivery-challans'] });
      void navigate('/sales/delivery-challans');
    },
    onError: (err) => {
      setConvertingId(null);
      setError(getErrorMessage(err));
    },
  });

  const cancel = useMutation({
    mutationFn: (id: number) => cancelSalesOrder(id),
    onSuccess: () => {
      setConfirmCancelId(null);
      setError(null);
      void qc.invalidateQueries({ queryKey: ['sales-orders'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const converting = convertMutation.isPending || convertToChallanMutation.isPending;

  return (
    <>
      <DocumentListPage
        titleKey="nav.salesOrders"
        newPath="/sales/orders/new"
        createLabelKey="phase1.newSalesOrder"
        detailPath={(id) => `/sales/orders/${id}`}
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
        rows={query.data?.results.map((o) => ({
          id: o.id,
          number: o.number,
          date: o.orderDate,
          partyName: o.customerName,
          status: o.status,
          grandTotal: o.grandTotal,
        }))}
        extraColumn={(row) => {
          if (row.status === 'DRAFT' && canWrite) {
            return (
              <Stack direction="row" spacing={1} justifyContent="flex-end">
                <Button
                  size="small"
                  variant="outlined"
                  disabled={converting && convertingId === row.id}
                  onClick={() => {
                    setConvertingId(row.id);
                    convertToChallanMutation.mutate(row.id);
                  }}
                >
                  {t('phase1.toChallan')}
                </Button>
                <Button
                  size="small"
                  disabled={converting && convertingId === row.id}
                  onClick={() => {
                    setConvertingId(row.id);
                    convertMutation.mutate(row.id);
                  }}
                >
                  {t('common.convert')}
                </Button>
              </Stack>
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
        body={t('history.confirmCancelSalesOrder')}
        confirmLabel={t('history.confirmCancelAction')}
        confirmColor="error"
        confirming={cancel.isPending}
        onClose={() => setConfirmCancelId(null)}
        onConfirm={() => confirmCancelId && cancel.mutate(confirmCancelId)}
      />
    </>
  );
}
