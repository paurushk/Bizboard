import { useMemo, useState } from 'react';
import { Link as RouterLink } from 'react-router-dom';
import Button from '@mui/material/Button';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import { completeWithConfirms } from '@/utils/completeWithConfirms';
import {
  cancelSalesCreditNote,
  completeSalesCreditNote,
  downloadSalesDocumentPdf,
  exportSalesCreditNotesCsv,
  listSalesCreditNotesPage,
} from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { useConfirmPrompt } from '@/hooks/useConfirmPrompt';
import { NoteRegisterFilterBar } from '@/components/billing/NoteRegisterFilters';
import { useNoteRegisterFilters } from '@/hooks/useNoteRegisterFilters';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { DocumentListPage } from '@/components/DocumentListPage';
import { printBlob, triggerBlobDownload } from '@/utils/blob';
import { t } from '@/i18n';
import { invalidateNoteQueries } from '@/utils/noteQueries';
import { canCancelDocuments, canExport, canIssueNotes } from '@/utils/permissions';

const PAGE_SIZE = 50;

export function CreditNotesPage() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const canWrite = canIssueNotes(user);
  const canCancel = canCancelDocuments(user);
  const [page, setPage] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const [confirmCancelId, setConfirmCancelId] = useState<number | null>(null);
  const filters = useNoteRegisterFilters();
  const confirmPrompt = useConfirmPrompt();
  const query = useQuery({
    queryKey: ['sales-credit-notes', page, filters.apiFilters],
    queryFn: () => listSalesCreditNotesPage({ page, pageSize: PAGE_SIZE, ...filters.apiFilters }),
  });
  const notesById = useMemo(
    () => new Map((query.data?.results ?? []).map((n) => [n.id, n])),
    [query.data],
  );
  const complete = useMutation({
    // F2-017: same confirm-retry helper the editor uses.
    mutationFn: (id: number) =>
      completeWithConfirms((extra) => completeSalesCreditNote(id, extra), {}, confirmPrompt.ask),
    onSuccess: () => {
      setError(null);
      invalidateNoteQueries(qc, 'credit');
    },
    onError: (err) => setError(getErrorMessage(err)),
  });
  const cancel = useMutation({
    mutationFn: (id: number) => cancelSalesCreditNote(id),
    onSuccess: () => {
      setError(null);
      setConfirmCancelId(null);
      invalidateNoteQueries(qc, 'credit');
    },
    onError: (err) => setError(getErrorMessage(err)),
  });
  const exportCsv = useMutation({
    mutationFn: () => exportSalesCreditNotesCsv(filters.apiFilters),
    onSuccess: (blob) => triggerBlobDownload(blob, 'sales-credit-notes.csv'),
    onError: (err) => setError(getErrorMessage(err)),
  });

  return (
    <>
      {confirmPrompt.dialog}
      <DocumentListPage
        titleKey="nav.creditNotes"
        newPath="/sales/credit-notes/new"
        createLabelKey="phase1.newCreditNote"
        detailPath={(id) => `/sales/credit-notes/${id}`}
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
        filters={
          <NoteRegisterFilterBar
            state={filters.state}
            rangeInvalid={filters.rangeInvalid}
            onChange={(patch) => {
              setPage(1);
              filters.set(patch);
            }}
            onExport={() => exportCsv.mutate()}
            exporting={exportCsv.isPending}
            canExport={canExport(user)}
          />
        }
        sourceColumn={{
          headerKey: 'phase1.sourceInvoice',
          render: (row) =>
            row.sourceId ? (
              <Button component={RouterLink} to={`/sales/history/${row.sourceId}`} size="small">
                {row.sourceNumber ?? row.sourceId}
              </Button>
            ) : (
              '—'
            ),
        }}
        rows={query.data?.results.map((n) => ({
          id: n.id,
          number: n.number,
          date: n.noteDate,
          partyName: n.customerName,
          status: n.status,
          grandTotal: n.grandTotal,
          sourceId: n.salesInvoice,
          sourceNumber: n.invoiceNumber,
        }))}
        rowActions={(row) => {
          const linkedReturn = notesById.get(row.id)?.salesReturn ?? null;
          return (
            <>
              {row.status === 'DRAFT' && canWrite ? (
                <Button size="small" disabled={complete.isPending} onClick={() => complete.mutate(row.id)}>
                  {t('common.complete')}
                </Button>
              ) : null}
              {row.status === 'COMPLETED' ? (
                <Button
                  size="small"
                  onClick={() =>
                    void downloadSalesDocumentPdf('credit-note', row.id)
                      .then((blob) => printBlob(blob))
                      .catch((err) => setError(getErrorMessage(err)))
                  }
                >
                  {t('billing.print')}
                </Button>
              ) : null}
              {row.status === 'COMPLETED' && linkedReturn ? (
                // CN-06: the credit note a sales return issued is cancelled by cancelling the return.
                <Button component={RouterLink} to="/sales/returns" size="small">
                  {t('phase1.cancelViaReturn')}
                </Button>
              ) : row.status === 'COMPLETED' && canCancel ? (
                <Button size="small" color="warning" onClick={() => setConfirmCancelId(row.id)}>
                  {t('common.cancel')}
                </Button>
              ) : null}
            </>
          );
        }}
      />
      <ConfirmDialog
        open={confirmCancelId !== null}
        title={t('common.confirm')}
        body={t('history.confirmCancelCreditNote')}
        confirmLabel={t('history.confirmCancelAction')}
        confirmColor="error"
        confirming={cancel.isPending}
        onClose={() => setConfirmCancelId(null)}
        onConfirm={() => confirmCancelId && cancel.mutate(confirmCancelId)}
      />
    </>
  );
}
