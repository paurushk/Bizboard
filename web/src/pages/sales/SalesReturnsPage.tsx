import { useEffect, useState } from 'react';
import Alert from '@mui/material/Alert';
import Autocomplete from '@mui/material/Autocomplete';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { getErrorMessage, userGestureIdempotencyKey } from '@/api/client';
import {
  completeSalesReturn,
  createSalesReturn,
  getSalesInvoice,
  listSalesInvoicesPage,
  listSalesReturns,
  listSalesReturnsPage,
} from '@/api/resources';
import {
  InvoiceReturnLineTable,
  activeSourceLines,
  invoiceItemsToSourceLines,
  todayIso,
  useDebouncedValue,
  type InvoiceSourceLine,
} from '@/components/billing';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { StatusChip } from '@/components/StatusChip';
import { t } from '@/i18n';
import type { SalesInvoice } from '@/types/domain';
import { formatMoney } from '@/utils/money';
import { canCreateSales } from '@/utils/permissions';
import { useAuth } from '@/auth/AuthContext';
import { useSubscriptionGate } from '@/hooks/useSubscriptionGate';
import { documentStatusTone, statusLabelKey } from '@/utils/status';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';

const PAGE_SIZE = 50;

export function SalesReturnsPage() {
  const { user } = useAuth();
  const { writesBlocked } = useSubscriptionGate();
  const canWrite = canCreateSales(user) && !writesBlocked;
  const qc = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const [page, setPage] = useState(1);
  const query = useQuery({
    queryKey: ['sales-returns', page],
    queryFn: () => listSalesReturnsPage({ page, pageSize: PAGE_SIZE }),
  });
  const [invoiceSearch, setInvoiceSearch] = useState('');
  const debouncedInvoiceSearch = useDebouncedValue(invoiceSearch, 250);
  const invoices = useQuery({
    queryKey: ['completed-sales', debouncedInvoiceSearch],
    queryFn: async () => {
      const res = await listSalesInvoicesPage({
        status: 'COMPLETED',
        q: debouncedInvoiceSearch.trim() || undefined,
        pageSize: PAGE_SIZE,
      });
      return res.results;
    },
  });

  const returns = query.data?.results ?? [];

  const [open, setOpen] = useState(false);
  const [invoice, setInvoice] = useState<SalesInvoice | null>(null);
  const [lines, setLines] = useState<InvoiceSourceLine[]>([]);
  const [reason, setReason] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    if (searchParams.get('create') !== '1') return;
    setOpen(true);
    const next = new URLSearchParams(searchParams);
    next.delete('create');
    setSearchParams(next, { replace: true });
  }, [searchParams, setSearchParams]);

  const onInvoicePick = async (inv: SalesInvoice | null) => {
    setInvoice(inv);
    if (!inv) {
      setLines([]);
      return;
    }
    const full = inv.items?.length ? inv : await getSalesInvoice(inv.id);
    setInvoice(full);
    // F2-013: subtract quantities already returned on prior return documents
    // for this invoice so the same units can't be returned twice.
    const returnedByProduct = new Map<number, number>();
    try {
      const prior = await listSalesReturns({ salesInvoice: String(full.id) });
      for (const ret of prior) {
        if (ret.status === 'CANCELLED') continue;
        for (const it of ret.items ?? []) {
          returnedByProduct.set(
            it.product,
            (returnedByProduct.get(it.product) ?? 0) + Number(it.quantity || 0),
          );
        }
      }
    } catch {
      /* best-effort — fall back to full invoice quantities */
    }
    setLines(invoiceItemsToSourceLines(full.items, returnedByProduct));
  };

  const createMutation = useMutation({
    mutationFn: async () => {
      if (!invoice) throw new Error(t('phase1.selectInvoice'));
      const selected = activeSourceLines(lines);
      if (selected.length === 0) throw new Error(t('phase1.selectInvoiceLines'));
      // F2-013: one key per gesture — a retry of create won't make a second
      // draft, and complete is idempotent too.
      const key = userGestureIdempotencyKey();
      const draft = await createSalesReturn({
        customer: invoice.customer,
        salesInvoice: invoice.id,
        returnDate: todayIso(),
        reason,
        items: selected.map((l) => ({
          product: l.product,
          quantity: l.quantity,
          unitPrice: l.unitPrice,
          gstRate: l.gstRate,
          condition: l.condition || 'SELLABLE',
        })),
      }, { idempotencyKey: key });
      return completeSalesReturn(draft.id, { idempotencyKey: `${key}-complete` });
    },
    onSuccess: () => {
      setOpen(false);
      setMessage('Sales return completed');
      setInvoice(null);
      setLines([]);
      setReason('');
      void qc.invalidateQueries({ queryKey: ['sales-returns'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <Typography variant="h4">{t('nav.salesReturns')}</Typography>
        {canWrite ? (
        <Button
          variant="contained"
          onClick={() => {
            setError(null);
            setOpen(true);
          }}
        >
          {t('phase1.newSalesReturn')}
        </Button>
        ) : null}
      </Stack>
      {message ? <Alert severity="success">{message}</Alert> : null}
      {error ? <HelpErrorAlert message={error} /> : null}
      {query.isLoading ? <LoadingState /> : null}
      {query.isError ? (
        <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />
      ) : null}
      {returns.length === 0 && query.isSuccess ? <EmptyState /> : null}
      {returns.length > 0 ? (
        <Paper sx={{ overflow: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t('common.number')}</TableCell>
                <TableCell>{t('common.date')}</TableCell>
                <TableCell>{t('billing.customer')}</TableCell>
                <TableCell>{t('common.status')}</TableCell>
                <TableCell align="right">{t('common.total')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {returns.map((r) => (
                <TableRow key={r.id}>
                  <TableCell>{r.number ?? r.id}</TableCell>
                  <TableCell>{r.returnDate}</TableCell>
                  <TableCell>{r.customerName}</TableCell>
                  <TableCell>
                    <StatusChip
                      tone={documentStatusTone(r.status)}
                      labelKey={statusLabelKey(r.status)}
                    />
                  </TableCell>
                  <TableCell align="right">{formatMoney(r.grandTotal)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Paper>
      ) : null}
      {query.data && (query.data.next || page > 1) ? (
        <Stack direction="row" spacing={1} justifyContent="flex-end" alignItems="center">
          <Typography variant="body2" color="text.secondary">
            {t('common.page')} {page}
          </Typography>
          <Button variant="outlined" size="small" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
            {t('common.previous')}
          </Button>
          <Button
            variant="outlined"
            size="small"
            disabled={!query.data.next}
            onClick={() => setPage((p) => p + 1)}
          >
            {t('common.next')}
          </Button>
        </Stack>
      ) : null}

      <Dialog open={open && canWrite} onClose={() => setOpen(false)} fullWidth maxWidth="md">
        <DialogTitle>New sales return</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            {/* Same-family fix as UXW2B-011/UXW2B-010: surface mutation errors inside
                the modal itself — a page-level Alert behind the Dialog is invisible. */}
            {error ? <HelpErrorAlert message={error} /> : null}
            {invoice && lines.length > 0 && activeSourceLines(lines).length === 0 ? (
              <Alert severity="warning">Select at least one item to return.</Alert>
            ) : null}
            <Autocomplete
              options={invoices.data ?? []}
              getOptionLabel={(o) => `${o.number ?? o.id} · ${o.customerName ?? ''}`}
              value={invoice}
              inputValue={invoiceSearch}
              onInputChange={(_, v) => setInvoiceSearch(v)}
              onChange={(_, v) => void onInvoicePick(v)}
              loading={invoices.isLoading}
              filterOptions={(x) => x}
              renderInput={(params) => <TextField {...params} label="Original invoice" placeholder="Search by invoice # or customer" />}
            />
            {lines.length > 0 ? (
              <InvoiceReturnLineTable lines={lines} onChange={setLines} />
            ) : null}
            <TextField
              label={t('common.reason')}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>{t('common.cancel')}</Button>
          <Button
            variant="contained"
            disabled={!invoice || activeSourceLines(lines).length === 0 || createMutation.isPending}
            onClick={() => createMutation.mutate()}
          >
            {t('common.complete')}
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}
