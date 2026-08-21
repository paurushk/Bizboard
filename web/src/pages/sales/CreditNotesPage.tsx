import { useState } from 'react';
import Button from '@mui/material/Button';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import {
  cancelSalesCreditNote,
  completeSalesCreditNote,
  downloadSalesDocumentPdf,
  listSalesCreditNotesPage,
} from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { DocumentListPage } from '@/components/DocumentListPage';
import { printBlob } from '@/utils/blob';
import { t } from '@/i18n';
import { canCreateSales } from '@/utils/permissions';

const PAGE_SIZE = 50;

export function CreditNotesPage() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const [page, setPage] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const query = useQuery({
    queryKey: ['sales-credit-notes', page],
    queryFn: () => listSalesCreditNotesPage({ page, pageSize: PAGE_SIZE }),
  });
  const complete = useMutation({
    mutationFn: (id: number) => completeSalesCreditNote(id),
    onSuccess: () => {
      setError(null);
      void qc.invalidateQueries({ queryKey: ['sales-credit-notes'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });
  const cancel = useMutation({
    mutationFn: (id: number) => cancelSalesCreditNote(id),
    onSuccess: () => {
      setError(null);
      void qc.invalidateQueries({ queryKey: ['sales-credit-notes'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  return (
    <DocumentListPage
      titleKey="nav.creditNotes"
      newPath="/sales/credit-notes/new"
      createLabelKey="phase1.newCreditNote"
      detailPath={(id) => `/sales/credit-notes/${id}`}
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
      rows={query.data?.results.map((n) => ({
        id: n.id,
        number: n.number,
        date: n.noteDate,
        partyName: n.customerName,
        status: n.status,
        grandTotal: n.grandTotal,
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
                void downloadSalesDocumentPdf('credit-note', row.id).then((blob) => printBlob(blob))
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
