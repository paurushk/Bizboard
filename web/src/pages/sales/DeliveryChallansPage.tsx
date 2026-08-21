import { useState } from 'react';
import Button from '@mui/material/Button';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import {
  cancelDeliveryChallan,
  completeDeliveryChallan,
  downloadSalesDocumentPdf,
  listDeliveryChallansPage,
} from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { DocumentListPage } from '@/components/DocumentListPage';
import { printBlob } from '@/utils/blob';
import { t } from '@/i18n';
import { canCreateSales } from '@/utils/permissions';

const PAGE_SIZE = 50;

export function DeliveryChallansPage() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const [page, setPage] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const query = useQuery({
    queryKey: ['delivery-challans', page],
    queryFn: () => listDeliveryChallansPage({ page, pageSize: PAGE_SIZE }),
  });
  const complete = useMutation({
    mutationFn: (id: number) => completeDeliveryChallan(id),
    onSuccess: () => {
      setError(null);
      void qc.invalidateQueries({ queryKey: ['delivery-challans'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });
  const cancel = useMutation({
    mutationFn: (id: number) => cancelDeliveryChallan(id),
    onSuccess: () => {
      setError(null);
      void qc.invalidateQueries({ queryKey: ['delivery-challans'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  return (
    <DocumentListPage
      titleKey="nav.deliveryChallans"
      newPath="/sales/delivery-challans/new"
      createLabelKey="phase1.newDeliveryChallan"
      detailPath={(id) => `/sales/delivery-challans/${id}`}
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
          {row.status === 'DRAFT' ? (
            <Button size="small" onClick={() => complete.mutate(row.id)}>
              {t('common.complete')}
            </Button>
          ) : null}
          {row.status === 'COMPLETED' ? (
            <Button
              size="small"
              onClick={() =>
                void downloadSalesDocumentPdf('delivery-challan', row.id).then((blob) => printBlob(blob))
              }
            >
              {t('billing.print')}
            </Button>
          ) : null}
          {row.status === 'COMPLETED' ? (
            <Button size="small" color="warning" onClick={() => cancel.mutate(row.id)}>
              {t('common.cancel')}
            </Button>
          ) : null}
        </>
      )}
    />
  );
}
