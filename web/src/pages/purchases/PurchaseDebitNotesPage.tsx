import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import { listPurchaseDebitNotesPage } from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { DocumentListPage } from '@/components/DocumentListPage';
import { canCreatePurchases } from '@/utils/permissions';

const PAGE_SIZE = 50;

export function PurchaseDebitNotesPage() {
  const { user } = useAuth();
  const [page, setPage] = useState(1);
  const query = useQuery({
    queryKey: ['purchase-debit-notes', page],
    queryFn: () => listPurchaseDebitNotesPage({ page, pageSize: PAGE_SIZE }),
  });
  return (
    <DocumentListPage
      titleKey="nav.purchaseDebitNotes"
      newPath="/purchases/debit-notes/new"
      createLabelKey="phase1.newPurchaseDebitNote"
      detailPath={(id) => `/purchases/debit-notes/${id}`}
      partyLabelKey="billing.supplier"
      loading={query.isLoading}
      error={query.isError ? getErrorMessage(query.error) : null}
      onRetry={() => void query.refetch()}
      showCreate={canCreatePurchases(user)}
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
    />
  );
}
