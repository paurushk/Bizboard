import { useState } from 'react';
import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import { convertSalesOrder, convertSalesOrderToChallan, listSalesOrdersPage } from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { DocumentListPage } from '@/components/DocumentListPage';
import { t } from '@/i18n';
import { canCreateSales } from '@/utils/permissions';

const PAGE_SIZE = 50;

export function SalesOrdersPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [page, setPage] = useState(1);
  const [convertingId, setConvertingId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
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

  return (
    <DocumentListPage
      titleKey="nav.salesOrders"
      newPath="/sales/orders/new"
      createLabelKey="phase1.newSalesOrder"
      detailPath={(id) => `/sales/orders/${id}`}
      partyLabelKey="billing.customer"
      loading={query.isLoading}
      error={error ?? (query.isError ? getErrorMessage(query.error) : null)}
      onRetry={() => void query.refetch()}
      showCreate={canCreateSales(user)}
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
      extraColumn={(row) =>
        row.status === 'DRAFT' ? (
          <Stack direction="row" spacing={1} justifyContent="flex-end">
            <Button
              size="small"
              variant="outlined"
              disabled={
                (convertMutation.isPending || convertToChallanMutation.isPending) &&
                convertingId === row.id
              }
              onClick={() => {
                setConvertingId(row.id);
                convertToChallanMutation.mutate(row.id);
              }}
            >
              To Challan
            </Button>
            <Button
              size="small"
              disabled={
                (convertMutation.isPending || convertToChallanMutation.isPending) &&
                convertingId === row.id
              }
              onClick={() => {
                setConvertingId(row.id);
                convertMutation.mutate(row.id);
              }}
            >
              {t('common.convert')}
            </Button>
          </Stack>
        ) : null
      }
    />
  );
}
