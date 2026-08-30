import { useState } from 'react';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import {
  cancelSalesDebitNote,
  completeSalesDebitNote,
  downloadSalesDocumentPdf,
  listSalesDebitNotesPage,
} from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { DocumentListPage } from '@/components/DocumentListPage';
import { printBlob } from '@/utils/blob';
import { t } from '@/i18n';
import { canCreateSales } from '@/utils/permissions';

const PAGE_SIZE = 50;

export function DebitNotesPage() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const [page, setPage] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const [confirmCancelId, setConfirmCancelId] = useState<number | null>(null);
  const query = useQuery({
    queryKey: ['sales-debit-notes', page],
    queryFn: () => listSalesDebitNotesPage({ page, pageSize: PAGE_SIZE }),
  });
  const complete = useMutation({
    mutationFn: (id: number) => completeSalesDebitNote(id),
    onSuccess: () => {
      setError(null);
      void qc.invalidateQueries({ queryKey: ['sales-debit-notes'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });
  const cancel = useMutation({
    mutationFn: (id: number) => cancelSalesDebitNote(id),
    onSuccess: () => {
      setError(null);
      setConfirmCancelId(null);
      void qc.invalidateQueries({ queryKey: ['sales-debit-notes'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  return (
    <>
      <DocumentListPage
        titleKey="nav.debitNotes"
        newPath="/sales/debit-notes/new"
        createLabelKey="phase1.newDebitNote"
        detailPath={(id) => `/sales/debit-notes/${id}`}
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
                  void downloadSalesDocumentPdf('debit-note', row.id).then((blob) => printBlob(blob))
                }
              >
                {t('billing.print')}
              </Button>
            ) : null}
            {row.status === 'COMPLETED' ? (
              <Button size="small" color="warning" onClick={() => setConfirmCancelId(row.id)}>
                {t('common.cancel')}
              </Button>
            ) : null}
          </>
        )}
      />
      <Dialog open={confirmCancelId !== null} onClose={() => setConfirmCancelId(null)}>
        <DialogTitle>{t('common.confirm')}</DialogTitle>
        <DialogContent>
          <Typography>Are you sure you want to cancel this debit note? This action cannot be undone.</Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmCancelId(null)}>{t('common.cancel')}</Button>
          <Button
            color="error"
            variant="contained"
            disabled={cancel.isPending}
            onClick={() => confirmCancelId && cancel.mutate(confirmCancelId)}
          >
            Confirm Cancel
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
