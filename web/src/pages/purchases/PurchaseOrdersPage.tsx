import { useState } from 'react';
import Button from '@mui/material/Button';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import { convertPurchaseOrder, listPurchaseOrdersPage } from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { DocumentListPage } from '@/components/DocumentListPage';
import { t } from '@/i18n';
import { canCreatePurchases } from '@/utils/permissions';

const PAGE_SIZE = 50;

export function PurchaseOrdersPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [page, setPage] = useState(1);
  const [convertingId, setConvertingId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
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

  return (
    <DocumentListPage
      titleKey="nav.purchaseOrders"
      newPath="/purchases/orders/new"
      createLabelKey="phase1.newPurchaseOrder"
      detailPath={(id) => `/purchases/orders/${id}`}
      partyLabelKey="billing.supplier"
      loading={query.isLoading}
      error={error ?? (query.isError ? getErrorMessage(query.error) : null)}
      onRetry={() => void query.refetch()}
      showCreate={canCreatePurchases(user)}
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
      extraColumn={(row) =>
        row.status === 'DRAFT' ? (
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
        ) : null
      }
    />
  );
}
