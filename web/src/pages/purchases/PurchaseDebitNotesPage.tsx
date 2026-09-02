import { useState } from 'react';
import Button from '@mui/material/Button';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import {
  cancelPurchaseDebitNote,
  completePurchaseDebitNote,
  listPurchaseDebitNotesPage,
} from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { DocumentListPage } from '@/components/DocumentListPage';
import { t } from '@/i18n';
import { canCancelDocuments, canCreatePurchases } from '@/utils/permissions';

const PAGE_SIZE = 50;

export function PurchaseDebitNotesPage() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const canWrite = canCreatePurchases(user);
  const canCancel = canCancelDocuments(user);
  const [page, setPage] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const [confirmCancelId, setConfirmCancelId] = useState<number | null>(null);
  const query = useQuery({
    queryKey: ['purchase-debit-notes', page],
    queryFn: () => listPurchaseDebitNotesPage({ page, pageSize: PAGE_SIZE }),
  });
  const complete = useMutation({
    mutationFn: (id: number) => completePurchaseDebitNote(id),
    onSuccess: () => {
      setError(null);
      void qc.invalidateQueries({ queryKey: ['purchase-debit-notes'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });
  const cancel = useMutation({
    mutationFn: (id: number) => cancelPurchaseDebitNote(id),
    onSuccess: () => {
      setError(null);
      setConfirmCancelId(null);
      void qc.invalidateQueries({ queryKey: ['purchase-debit-notes'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });
  return (
    <>
      <DocumentListPage
        titleKey="nav.purchaseDebitNotes"
        newPath="/purchases/debit-notes/new"
        createLabelKey="phase1.newPurchaseDebitNote"
        detailPath={(id) => `/purchases/debit-notes/${id}`}
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
        rows={query.data?.results.map((n) => ({
          id: n.id,
          number: n.number,
          date: n.noteDate,
          partyName: n.supplierName,
          status: n.status,
          grandTotal: n.grandTotal,
        }))}
        rowActions={(row) => (
          <>
            {row.status === 'DRAFT' && canWrite ? (
              <Button size="small" disabled={complete.isPending} onClick={() => complete.mutate(row.id)}>
                {t('common.complete')}
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
      <ConfirmDialog
        open={confirmCancelId !== null}
        title={t('common.confirm')}
        body={t('history.confirmCancelPurchaseDebitNote')}
        confirmLabel={t('history.confirmCancelAction')}
        confirmColor="error"
        confirming={cancel.isPending}
        onClose={() => setConfirmCancelId(null)}
        onConfirm={() => confirmCancelId && cancel.mutate(confirmCancelId)}
      />
    </>
  );
}
