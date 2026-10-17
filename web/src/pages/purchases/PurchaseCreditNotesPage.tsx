import { useState } from 'react';
import { Link as RouterLink } from 'react-router-dom';
import Button from '@mui/material/Button';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getErrorMessage, userGestureIdempotencyKey } from '@/api/client';
import {
  cancelPurchaseCreditNote,
  completePurchaseCreditNote,
  exportPurchaseCreditNotesCsv,
  listPurchaseCreditNotesPage,
} from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { NoteRegisterFilterBar } from '@/components/billing/NoteRegisterFilters';
import { useNoteRegisterFilters } from '@/hooks/useNoteRegisterFilters';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { DocumentListPage } from '@/components/DocumentListPage';
import { t } from '@/i18n';
import { completeWithConfirms } from '@/utils/completeWithConfirms';
import { triggerBlobDownload } from '@/utils/blob';
import { invalidatePurchaseNoteQueries } from '@/utils/noteQueries';
import { canCancelDocuments, canCreatePurchases, canExport } from '@/utils/permissions';

const PAGE_SIZE = 50;

export function PurchaseCreditNotesPage() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const canWrite = canCreatePurchases(user);
  const canCancel = canCancelDocuments(user);
  const [page, setPage] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const [confirmCancelId, setConfirmCancelId] = useState<number | null>(null);
  const filters = useNoteRegisterFilters();
  const query = useQuery({
    queryKey: ['purchase-credit-notes', page, filters.apiFilters],
    queryFn: () => listPurchaseCreditNotesPage({ page, pageSize: PAGE_SIZE, ...filters.apiFilters }),
  });
  const complete = useMutation({
    // CR-129: prompt + retry on paid-invoice / price-override confirm codes.
    mutationFn: (id: number) =>
      completeWithConfirms((extra) =>
        completePurchaseCreditNote(id, {
          idempotencyKey: userGestureIdempotencyKey(),
          confirmPaidInvoice: extra.confirmPaidInvoice,
          confirmPriceOverride: extra.confirmPriceOverride,
        }),
      ),
    onSuccess: () => {
      setError(null);
      invalidatePurchaseNoteQueries(qc, 'credit');
    },
    onError: (err) => setError(getErrorMessage(err)),
  });
  const cancel = useMutation({
    mutationFn: (id: number) => cancelPurchaseCreditNote(id),
    onSuccess: () => {
      setError(null);
      setConfirmCancelId(null);
      invalidatePurchaseNoteQueries(qc, 'credit');
    },
    onError: (err) => setError(getErrorMessage(err)),
  });
  const exportCsv = useMutation({
    mutationFn: () => exportPurchaseCreditNotesCsv(filters.apiFilters),
    onSuccess: (blob) => triggerBlobDownload(blob, 'purchase-credit-notes.csv'),
    onError: (err) => setError(getErrorMessage(err)),
  });
  return (
    <>
      <DocumentListPage
        titleKey="nav.purchaseCreditNotes"
        newPath="/purchases/credit-notes/new"
        createLabelKey="phase1.newPurchaseCreditNote"
        detailPath={(id) => `/purchases/credit-notes/${id}`}
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
              <Button component={RouterLink} to={`/purchases/history/${row.sourceId}`} size="small">
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
          partyName: n.supplierName,
          status: n.status,
          grandTotal: n.grandTotal,
          sourceId: n.purchaseInvoice ?? null,
          sourceNumber: n.invoiceNumber ?? null,
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
        body={t('history.confirmCancelPurchaseCreditNote')}
        confirmLabel={t('history.confirmCancelAction')}
        confirmColor="error"
        confirming={cancel.isPending}
        onClose={() => setConfirmCancelId(null)}
        onConfirm={() => confirmCancelId && cancel.mutate(confirmCancelId)}
      />
    </>
  );
}
