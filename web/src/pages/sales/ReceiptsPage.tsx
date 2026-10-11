import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Checkbox from '@mui/material/Checkbox';
import Chip from '@mui/material/Chip';
import Menu from '@mui/material/Menu';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import TableSortLabel from '@mui/material/TableSortLabel';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import useMediaQuery from '@mui/material/useMediaQuery';
import { getErrorMessage, userGestureIdempotencyKey } from '@/api/client';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import {
  exportReceiptsCsv,
  getReceiptsSummary,
  listReceiptsPage,
  refundGatewayPayment,
  setReceiptChequeStatus,
  voidReceipt,
} from '@/api/resources';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { useDebouncedValue } from '@/hooks/useDebouncedValue';
import { useAuth } from '@/auth/AuthContext';
import { PageTitle } from '@/contextHelp';
import { t, useLocale } from '@/i18n';
import { trackShopFloor } from '@/lib/telemetry';
import { useReceiptOutbox } from '@/pages/sales/useReceiptOutbox';
import type { CustomerReceipt } from '@/types/domain';
import { formatMoney, toNumber } from '@/utils/money';
import { AllocationManagerDialog } from '@/pages/sales/AllocationManagerDialog';
import { BulkAllocateDialog } from '@/pages/sales/BulkAllocateDialog';
import { BulkSendDialog } from '@/pages/sales/BulkSendDialog';
import { NewReceiptDialog } from '@/pages/sales/NewReceiptDialog';
import {
  CorrectClosedTillDialog,
  EditReceiptDialog,
  ReassignReceiptDialog,
} from '@/pages/sales/ReceiptCorrectionDialogs';
import { ReceiptVoucherDialog } from '@/pages/sales/ReceiptVoucherDialog';
import { receiptStatusChips } from '@/pages/sales/receiptStatus';
import { RefundAdvanceDialog } from '@/pages/sales/RefundAdvanceDialog';
import { SendReceiptDialog } from '@/pages/sales/SendReceiptDialog';
import { VoidReceiptDialog } from '@/pages/sales/VoidReceiptDialog';
import { triggerBlobDownload } from '@/utils/blob';
import {
  canCancelDocuments,
  canCorrectClosedTill,
  canCreatePayments,
  canExport,
  isOwner,
} from '@/utils/permissions';
import { useSubscriptionGate } from '@/hooks/useSubscriptionGate';

// Text for screen readers only (the actions column has no visible heading).
const visuallyHidden = {
  position: 'absolute',
  width: 1,
  height: 1,
  overflow: 'hidden',
  clip: 'rect(0 0 0 0)',
  whiteSpace: 'nowrap',
} as const;

const PAGE_SIZES = [25, 50, 100] as const;

/** Columns the server can sort by (payments.views.RECEIPT_ORDERING_FIELDS). */
type SortField = 'receipt_date' | 'amount' | 'number' | 'customer__name' | 'status';

/** Can this row be picked for "apply to oldest bills"? An advance that is still free to apply. */
function appliable(r: CustomerReceipt): boolean {
  return (
    (r.status === undefined || r.status === 'POSTED') &&
    toNumber(r.allocatable ?? r.unallocated) > 0 &&
    !r.customerIsWalkIn &&
    !(r.mode === 'CHEQUE' && r.chequeStatus === 'PENDING_CLEARANCE')
  );
}

export function ReceiptsPage() {
  useLocale();
  const { user } = useAuth();
  const { writesBlocked } = useSubscriptionGate();
  const canWrite = canCreatePayments(user) && !writesBlocked;
  const canCancel = canCancelDocuments(user) && !writesBlocked;
  const canExportCsv = canExport(user);
  const canFixTill = canCorrectClosedTill(user) && !writesBlocked;
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [errorSource, setErrorSource] = useState<unknown>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [viewReceipt, setViewReceipt] = useState<CustomerReceipt | null>(null);
  const [manage, setManage] = useState<CustomerReceipt | null>(null);
  const [editing, setEditing] = useState<CustomerReceipt | null>(null);
  const [refunding, setRefunding] = useState<CustomerReceipt | null>(null);
  const [reassigning, setReassigning] = useState<CustomerReceipt | null>(null);
  const [correcting, setCorrecting] = useState<CustomerReceipt | null>(null);
  const [sending, setSending] = useState<CustomerReceipt | null>(null);
  const [menu, setMenu] = useState<{ anchor: HTMLElement; receipt: CustomerReceipt } | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [bulkOpen, setBulkOpen] = useState(false);
  const [bulkSendOpen, setBulkSendOpen] = useState(false);

  const narrowVoid = useMediaQuery('(max-width:899.95px)');
  const [voidId, setVoidId] = useState<number | null>(null);
  const [voidError, setVoidError] = useState<string | null>(null);
  const [voidErrorSource, setVoidErrorSource] = useState<unknown>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState<number>(50);
  const [goTo, setGoTo] = useState('');
  const [sort, setSort] = useState<{ field: SortField; dir: 'asc' | 'desc' } | null>(null);
  // An alert can link here with the receipt it is about (?q=RCT-...).
  const [searchParams] = useSearchParams();
  const [filterQuery, setFilterQuery] = useState(() => (searchParams.get('q') ?? '').slice(0, 100));
  const debouncedFilterQuery = useDebouncedValue(filterQuery, 300);
  const [modeFilter, setModeFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [reconciledFilter, setReconciledFilter] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  // An inverted range is a 400 on the server; hold the request until it is fixed.
  const rangeInvalid = Boolean(dateFrom && dateTo && dateFrom > dateTo);
  // The server ignores searches shorter than this, except an exact receipt number.
  const trimmedQuery = debouncedFilterQuery.trim();
  // One filter object feeds the list, the totals and the export, so they always agree.
  const filters = {
    q: trimmedQuery || undefined,
    mode: modeFilter || undefined,
    status: statusFilter || undefined,
    reconciled: reconciledFilter || undefined,
    date_from: dateFrom || undefined,
    date_to: dateTo || undefined,
  };
  const ordering = sort ? `${sort.dir === 'desc' ? '-' : ''}${sort.field}` : undefined;
  const filtersActive = Boolean(filterQuery || modeFilter || statusFilter || reconciledFilter || dateFrom || dateTo);

  const query = useQuery({
    queryKey: ['receipts', page, pageSize, ordering, filters],
    queryFn: () => listReceiptsPage({ page, pageSize, ordering, ...filters }),
    enabled: !rangeInvalid,
  });
  const summary = useQuery({
    queryKey: ['receipts-summary', filters],
    queryFn: () => getReceiptsSummary(filters),
    enabled: !rangeInvalid,
  });
  const exportMutation = useMutation({
    mutationFn: () => exportReceiptsCsv({ ...filters, ordering }),
    onSuccess: (blob) => {
      triggerBlobDownload(blob, 'customer-receipts.csv');
      setMessage(t('receipts.exportStarted'));
    },
    onError: (err) => {
      setError(getErrorMessage(err));
      setErrorSource(err);
    },
  });

  const refreshAll = () => {
    void qc.invalidateQueries({ queryKey: ['receipts'] });
    void qc.invalidateQueries({ queryKey: ['receipts-summary'] });
    void qc.invalidateQueries({ queryKey: ['sales-invoices-open'] });
    void qc.invalidateQueries({ queryKey: ['receipt-manage-bills'] });
  };
  const done = (text: string) => {
    setMessage(text);
    setError(null);
    setErrorSource(null);
    refreshAll();
  };

  const voidMutation = useMutation({
    mutationFn: ({ id, reason }: { id: number; reason: string }) =>
      voidReceipt(id, reason, { idempotencyKey: userGestureIdempotencyKey() }),
    onSuccess: () => {
      trackShopFloor('document_voided', { feature: 'form' });
      setMessage(t('billing.receiptVoided'));
      // Close only now: a refused void keeps the dialog, and the reason typed in it.
      setVoidId(null);
      setVoidError(null);
      setVoidErrorSource(null);
      refreshAll();
    },
    onError: (err) => {
      setVoidError(getErrorMessage(err));
      setVoidErrorSource(err);
    },
  });

  const chequeStatusMutation = useMutation({
    mutationFn: ({ id, chequeStatus }: { id: number; chequeStatus: string }) =>
      setReceiptChequeStatus(id, chequeStatus),
    onSuccess: (receipt) => {
      setMessage(receipt.chequeStatus === 'BOUNCED' ? t('billing.bounceCheque') : t('billing.clearCheque'));
      refreshAll();
    },
    onError: (err) => {
      setError(getErrorMessage(err));
      setErrorSource(err);
    },
  });

  const gatewayRefund = useMutation({
    mutationFn: (gatewayPaymentId: number) => refundGatewayPayment(gatewayPaymentId),
    onSuccess: () => done(t('receipts.gatewayRefundDone')),
    onError: (err) => {
      setError(getErrorMessage(err));
      setErrorSource(err);
    },
  });

  const outbox = useReceiptOutbox(user ? { companyId: user.companyId ?? 0, userId: user.id } : null, (count) => {
    setMessage(t('receipts.offlineSent', { count }));
    refreshAll();
  });

  const receipts = query.data?.results ?? [];
  const showSource = receipts.some((row) => Boolean(row.source && row.source !== 'MANUAL'));
  const showBank = receipts.some((row) => Boolean(row.utr || row.bankAccountName || row.chequeNumber || row.utrWarning));
  const voidTarget = receipts.find((r) => r.id === voidId);
  const pageCount = Math.max(1, Math.ceil((query.data?.count ?? receipts.length) / pageSize));
  const selectable = receipts.filter(appliable);
  const selectedRows = receipts.filter((r) => selected.has(r.id));
  const allSelected = selectable.length > 0 && selectable.every((r) => selected.has(r.id));

  const resetPaging = () => {
    setPage(1);
    setSelected(new Set());
  };
  const toggleSort = (field: SortField) => {
    setSort((current) =>
      current?.field === field
        ? current.dir === 'asc'
          ? { field, dir: 'desc' }
          : null
        : { field, dir: field === 'receipt_date' || field === 'amount' ? 'desc' : 'asc' },
    );
    resetPaging();
  };
  const sortHeader = (field: SortField, label: string, align?: 'right') => {
    const active = sort?.field === field;
    return (
      <TableCell align={align} sortDirection={active ? sort!.dir : false}>
        <TableSortLabel
          active={active}
          direction={active ? sort!.dir : 'asc'}
          onClick={() => toggleSort(field)}
          aria-label={t('receipts.sortBy', { column: label })}
        >
          {label}
        </TableSortLabel>
      </TableCell>
    );
  };
  const jump = () => {
    const target = Math.min(Math.max(1, Math.floor(Number(goTo) || 1)), pageCount);
    setPage(target);
    setGoTo('');
  };

  const openNew = () => {
    setError(null);
    setErrorSource(null);
    setOpen(true);
  };

  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <PageTitle>{t('nav.receipts')}</PageTitle>
        {canWrite ? (
          <Button variant="contained" onClick={openNew}>
            {t('phase1.newReceipt')}
          </Button>
        ) : null}
      </Stack>
      {message ? <Alert severity="success">{message}</Alert> : null}
      {error ? <HelpErrorAlert message={error} error={errorSource} /> : null}

      {outbox.items.length > 0 ? (
        <Alert
          severity={outbox.items.some((row) => row.status === 'conflict') ? 'warning' : 'info'}
          action={
            <Button color="inherit" size="small" onClick={() => void outbox.flush()} disabled={outbox.flushing}>
              {t('receipts.offlineRetry')}
            </Button>
          }
        >
          <Typography variant="subtitle2" component="p">
            {t('receipts.offlineTitle')} ({outbox.items.length})
          </Typography>
          <Stack spacing={0.5} sx={{ mt: 0.5 }}>
            {outbox.items.map((row) => (
              <Stack key={row.id} direction="row" spacing={1} alignItems="center" useFlexGap flexWrap="wrap">
                <Typography variant="body2">
                  {row.customerName} · {formatMoney(row.payload.amount)} · {row.payload.receiptDate}
                </Typography>
                <Chip
                  size="small"
                  variant="outlined"
                  color={row.status === 'conflict' ? 'error' : 'default'}
                  label={row.status === 'conflict' ? t('receipts.offlineNeedsAttention') : t('receipts.waitingToSend')}
                />
                {row.error ? (
                  <Typography variant="caption">{t('receipts.offlineConflict', { reason: row.error })}</Typography>
                ) : null}
                {row.status === 'conflict' ? (
                  <>
                    <Button size="small" onClick={() => void outbox.retry(row.id)}>
                      {t('receipts.offlineRetry')}
                    </Button>
                    <Button size="small" color="warning" onClick={() => void outbox.discard(row.id)}>
                      {t('receipts.offlineDiscard')}
                    </Button>
                  </>
                ) : null}
              </Stack>
            ))}
          </Stack>
        </Alert>
      ) : null}

      {summary.data ? (
        <Box>
          <Box
            display="grid"
            gridTemplateColumns={{ xs: '1fr 1fr', sm: toNumber(summary.data.refunded) > 0 ? 'repeat(5, 1fr)' : 'repeat(4, 1fr)' }}
            gap={2}
            role="group"
            aria-label={t('receipts.kpiNote', { excluded: summary.data.excludedCount })}
          >
            <Paper sx={{ p: 1.5, textAlign: 'center' }}>
              <Typography variant="caption" color="text.secondary">{t('receipts.kpiCollected')}</Typography>
              <Typography variant="h6" component="p">{formatMoney(summary.data.collected)}</Typography>
            </Paper>
            <Paper sx={{ p: 1.5, textAlign: 'center' }}>
              <Typography variant="caption" color="text.secondary">{t('receipts.allocated')}</Typography>
              <Typography variant="h6" component="p">{formatMoney(summary.data.allocated)}</Typography>
            </Paper>
            <Paper sx={{ p: 1.5, textAlign: 'center' }}>
              <Typography variant="caption" color="text.secondary">{t('receipts.kpiAdvance')}</Typography>
              <Typography variant="h6" component="p" color="info.main">{formatMoney(summary.data.advance)}</Typography>
            </Paper>
            <Paper sx={{ p: 1.5, textAlign: 'center' }}>
              <Typography variant="caption" color="text.secondary">{t('receipts.kpiChequesPending')}</Typography>
              <Typography variant="h6" component="p" color={toNumber(summary.data.chequesPending) > 0 ? 'warning.main' : undefined}>
                {formatMoney(summary.data.chequesPending)}
              </Typography>
            </Paper>
            {toNumber(summary.data.refunded) > 0 ? (
              <Paper sx={{ p: 1.5, textAlign: 'center' }}>
                <Typography variant="caption" color="text.secondary">{t('receipts.kpiRefunded')}</Typography>
                <Typography variant="h6" component="p">{formatMoney(summary.data.refunded ?? 0)}</Typography>
              </Paper>
            ) : null}
          </Box>
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
            {t('receipts.kpiNote', { excluded: summary.data.excludedCount })}
            {toNumber(summary.data.chequesPending) > 0
              ? ` ${t('receipts.kpiChequeNote', { amount: formatMoney(summary.data.chequesPending) })}`
              : ''}
          </Typography>
        </Box>
      ) : summary.isError ? (
        <Typography variant="caption" color="text.secondary">{t('receipts.kpiUnavailable')}</Typography>
      ) : null}

      <Paper sx={{ p: 1.5 }}>
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5} alignItems={{ xs: 'stretch', md: 'center' }} useFlexGap flexWrap="wrap">
          <TextField
            size="small"
            type="search"
            label={t('receipts.searchLabel')}
            placeholder={t('receipts.searchPlaceholder')}
            value={filterQuery}
            onChange={(e) => {
              setFilterQuery(e.target.value);
              resetPaging();
            }}
            slotProps={{ htmlInput: { maxLength: 100 } }}
            sx={{ flex: 1, minWidth: { xs: 0, md: 240 } }}
          />
          <TextField
            select
            size="small"
            label={t('receipts.mode')}
            value={modeFilter}
            onChange={(e) => {
              setModeFilter(e.target.value);
              resetPaging();
            }}
            sx={{ minWidth: 120 }}
          >
            <MenuItem value="">{t('common.all')}</MenuItem>
            {/* CREDIT stays filterable so receipts recorded before it was refused stay findable. */}
            {(['CASH', 'UPI', 'BANK', 'CARD', 'CREDIT', 'CHEQUE'] as const).map((m) => (
              <MenuItem key={m} value={m}>{m}</MenuItem>
            ))}
          </TextField>
          <TextField
            select
            size="small"
            label={t('common.status')}
            value={statusFilter}
            onChange={(e) => {
              setStatusFilter(e.target.value);
              resetPaging();
            }}
            sx={{ minWidth: 120 }}
          >
            <MenuItem value="">{t('common.all')}</MenuItem>
            <MenuItem value="POSTED">{t('receipts.statusPosted')}</MenuItem>
            <MenuItem value="VOIDED">{t('receipts.statusVoided')}</MenuItem>
            <MenuItem value="REFUNDED">{t('receipts.statusRefunded')}</MenuItem>
          </TextField>
          <TextField
            select
            size="small"
            label={t('receipts.reconciledFilter')}
            value={reconciledFilter}
            onChange={(e) => {
              setReconciledFilter(e.target.value);
              resetPaging();
            }}
            sx={{ minWidth: 140 }}
          >
            <MenuItem value="">{t('common.all')}</MenuItem>
            <MenuItem value="true">{t('receipts.reconciledYes')}</MenuItem>
            <MenuItem value="false">{t('receipts.reconciledNo')}</MenuItem>
          </TextField>
          <TextField
            size="small"
            type="date"
            label={t('receipts.dateFrom')}
            value={dateFrom}
            onChange={(e) => {
              setDateFrom(e.target.value);
              resetPaging();
            }}
            error={rangeInvalid}
            slotProps={{ inputLabel: { shrink: true } }}
          />
          <TextField
            size="small"
            type="date"
            label={t('receipts.dateTo')}
            value={dateTo}
            onChange={(e) => {
              setDateTo(e.target.value);
              resetPaging();
            }}
            error={rangeInvalid}
            helperText={rangeInvalid ? t('receipts.rangeInvalid') : undefined}
            slotProps={{ inputLabel: { shrink: true } }}
          />
          {filtersActive ? (
            <Button
              size="small"
              onClick={() => {
                setFilterQuery('');
                setModeFilter('');
                setStatusFilter('');
                setReconciledFilter('');
                setDateFrom('');
                setDateTo('');
                resetPaging();
              }}
            >
              {t('common.clearFilters')}
            </Button>
          ) : null}
          {canExportCsv ? (
            <Button
              size="small"
              variant="outlined"
              disabled={exportMutation.isPending || rangeInvalid}
              onClick={() => exportMutation.mutate()}
            >
              {t('receipts.exportCsv')}
            </Button>
          ) : null}
        </Stack>
      </Paper>

      {selected.size > 0 ? (
        <Alert
          severity="info"
          icon={false}
          action={
            <Stack direction="row" spacing={1}>
              {canWrite ? (
                <Button size="small" variant="contained" onClick={() => setBulkOpen(true)}>
                  {t('receipts.bulkAllocate')}
                </Button>
              ) : null}
              <Button size="small" onClick={() => setBulkSendOpen(true)}>
                {t('receipts.bulkSend')}
              </Button>
              <Button size="small" color="inherit" onClick={() => setSelected(new Set())}>
                {t('receipts.bulkClear')}
              </Button>
            </Stack>
          }
        >
          {t('receipts.selectedCount', { count: selected.size })}
        </Alert>
      ) : null}

      {query.isLoading ? <LoadingState /> : null}
      {query.isError ? (
        <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />
      ) : null}
      {query.data && receipts.length === 0 ? (
        <EmptyState
          description={t('receipts.empty')}
          action={
            canWrite ? (
              <Button variant="contained" onClick={openNew}>
                {t('phase1.newReceipt')}
              </Button>
            ) : undefined
          }
        />
      ) : null}
      {receipts.length > 0 ? (
        <Paper tabIndex={0} role="region" aria-label={t('common.scrollableTable')} sx={{ overflow: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                {canWrite ? (
                  <TableCell padding="checkbox">
                    <Checkbox
                      size="small"
                      checked={allSelected}
                      indeterminate={!allSelected && selectable.some((r) => selected.has(r.id))}
                      disabled={selectable.length === 0}
                      onChange={(e) =>
                        setSelected(e.target.checked ? new Set(selectable.map((r) => r.id)) : new Set())
                      }
                      slotProps={{ input: { 'aria-label': t('receipts.selectAllRows') } }}
                    />
                  </TableCell>
                ) : null}
                {sortHeader('number', t('common.number'))}
                {sortHeader('receipt_date', t('common.date'))}
                {sortHeader('customer__name', t('billing.customer'))}
                <TableCell>{t('receipts.mode')}</TableCell>
                {sortHeader('status', t('receipts.status'))}
                {showSource ? <TableCell>{t('receipts.source')}</TableCell> : null}
                {showBank ? <TableCell>{t('receipts.utrBank')}</TableCell> : null}
                {sortHeader('amount', t('common.amount'), 'right')}
                <TableCell align="right">{t('receipts.allocated')}</TableCell>
                <TableCell sx={{ position: 'relative' }}>
                  <Box component="span" sx={visuallyHidden}>
                    {t('common.actions')}
                  </Box>
                </TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {receipts.map((r) => {
                const unallocated = toNumber(r.unallocated);
                const live = !r.status || r.status === 'POSTED';
                const gateway = r.source === 'GATEWAY' || Boolean(r.gatewayPayment);
                return (
                  <TableRow key={r.id} selected={selected.has(r.id)}>
                    {canWrite ? (
                      <TableCell padding="checkbox">
                        <Checkbox
                          size="small"
                          disabled={!appliable(r)}
                          checked={selected.has(r.id)}
                          onChange={(e) =>
                            setSelected((current) => {
                              const next = new Set(current);
                              if (e.target.checked) next.add(r.id);
                              else next.delete(r.id);
                              return next;
                            })
                          }
                          slotProps={{ input: { 'aria-label': t('receipts.selectRow', { number: r.number ?? String(r.id) }) } }}
                        />
                      </TableCell>
                    ) : null}
                    <TableCell>
                      <Button
                        variant="text"
                        size="small"
                        sx={{ p: 0, minWidth: 0, textTransform: 'none', fontWeight: 600, color: 'inherit' }}
                        aria-label={t('receipts.openVoucher', {
                          number: r.number ?? String(r.id),
                          customer: r.customerName ?? '',
                        })}
                        onClick={() => setViewReceipt(r)}
                      >
                        {r.number ?? r.id}
                      </Button>
                    </TableCell>
                    <TableCell>{r.receiptDate}</TableCell>
                    <TableCell>{r.customerName}</TableCell>
                    <TableCell>{r.mode}</TableCell>
                    <TableCell>
                      <Stack direction="row" spacing={0.5} useFlexGap flexWrap="wrap">
                        {receiptStatusChips(r).map((chip) => (
                          <Chip key={chip.key} size="small" label={chip.label} color={chip.color} variant="outlined" />
                        ))}
                        {r.reconciled ? (
                          <Chip size="small" label={t('receipts.reconciled')} color="default" variant="outlined" />
                        ) : null}
                        {r.reviewFlags?.includes('invoice_returned_after_payment') ? (
                          <Chip
                            size="small"
                            color="warning"
                            label={t('receipts.reviewInvoiceReturned')}
                            title={t('receipts.reviewInvoiceReturned')}
                          />
                        ) : null}
                      </Stack>
                    </TableCell>
                    {showSource ? (
                      <TableCell>
                        {r.source && r.source !== 'MANUAL' ? (
                          <Chip size="small" variant="outlined" label={r.source} />
                        ) : (
                          '—'
                        )}
                      </TableCell>
                    ) : null}
                    {showBank ? (
                      <TableCell>
                        {r.mode === 'CHEQUE'
                          ? [r.chequeNumber, r.chequeBankName, r.chequeStatus].filter(Boolean).join(' · ') || '—'
                          : r.utr ?? r.bankAccountName ?? '—'}
                        {r.utrWarning ? (
                          <Chip size="small" color="warning" sx={{ ml: 1 }} label={t('receipts.utrWarn')} title={r.utrWarning} />
                        ) : null}
                      </TableCell>
                    ) : null}
                    <TableCell align="right">{formatMoney(r.amount)}</TableCell>
                    <TableCell align="right">
                      {formatMoney(r.allocated)}
                      {live && unallocated > 0 ? (
                        <Chip
                          size="small"
                          color="info"
                          sx={{ ml: 1 }}
                          label={t('receipts.advance', { amount: formatMoney(unallocated) })}
                        />
                      ) : null}
                    </TableCell>
                    <TableCell align="right">
                      {!live ? null : canWrite || canCancel || canFixTill ? (
                        <Stack direction="row" spacing={0.5} justifyContent="flex-end" useFlexGap flexWrap="wrap">
                          {canWrite && !gateway && r.mode === 'CHEQUE' && r.chequeStatus === 'PENDING_CLEARANCE' ? (
                            <Button
                              size="small"
                              disabled={chequeStatusMutation.isPending}
                              onClick={() => chequeStatusMutation.mutate({ id: r.id, chequeStatus: 'CLEARED' })}
                            >
                              {t('billing.clearCheque')}
                            </Button>
                          ) : null}
                          {canWrite &&
                          !gateway &&
                          r.mode === 'CHEQUE' &&
                          (r.chequeStatus === 'PENDING_CLEARANCE' || r.chequeStatus === 'CLEARED') ? (
                            <Button
                              size="small"
                              color="warning"
                              disabled={chequeStatusMutation.isPending}
                              onClick={() => {
                                if (window.confirm(t('billing.confirmBounceCheque'))) {
                                  chequeStatusMutation.mutate({ id: r.id, chequeStatus: 'BOUNCED' });
                                }
                              }}
                            >
                              {t('billing.bounceCheque')}
                            </Button>
                          ) : null}
                          {canWrite && !gateway && canCancel ? (
                            <Button
                              size="small"
                              color="warning"
                              disabled={voidMutation.isPending}
                              onClick={() => {
                                setVoidId(r.id);
                                setVoidError(null);
                                setVoidErrorSource(null);
                              }}
                            >
                              {t('billing.voidAction')}
                            </Button>
                          ) : null}
                          {canWrite && unallocated > 0 ? (
                            <Button size="small" variant="outlined" onClick={() => setManage(r)}>
                              {t('receipts.allocate')}
                            </Button>
                          ) : null}
                          <Button
                            size="small"
                            aria-haspopup="menu"
                            aria-label={`${t('common.actions')} ${r.number ?? r.id}`}
                            onClick={(e) => setMenu({ anchor: e.currentTarget, receipt: r })}
                          >
                            ⋯
                          </Button>
                        </Stack>
                      ) : null}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
          <Stack
            direction={{ xs: 'column', sm: 'row' }}
            justifyContent="space-between"
            alignItems={{ xs: 'stretch', sm: 'center' }}
            spacing={1.5}
            p={2}
          >
            <Typography variant="body2" color="text.secondary">
              {t('common.pageOf', {
                page,
                pages: pageCount,
                total: query.data?.count ?? receipts.length,
              })}
            </Typography>
            <Stack direction="row" spacing={1} alignItems="center" useFlexGap flexWrap="wrap">
              <TextField
                select
                size="small"
                label={t('receipts.pageSize')}
                value={pageSize}
                onChange={(e) => {
                  setPageSize(Number(e.target.value));
                  resetPaging();
                }}
                sx={{ minWidth: 110 }}
              >
                {PAGE_SIZES.map((size) => (
                  <MenuItem key={size} value={size}>
                    {size}
                  </MenuItem>
                ))}
              </TextField>
              <TextField
                size="small"
                type="number"
                label={t('receipts.goToPage')}
                value={goTo}
                onChange={(e) => setGoTo(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') jump();
                }}
                slotProps={{ htmlInput: { min: 1, max: pageCount } }}
                sx={{ width: 120 }}
              />
              <Button size="small" onClick={jump} disabled={!goTo}>
                {t('receipts.goToPageGo')}
              </Button>
              <Button
                size="small"
                disabled={page <= 1 || query.isFetching}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
              >
                {t('common.previous')}
              </Button>
              <Button
                size="small"
                disabled={!query.data?.next || query.isFetching}
                onClick={() => setPage((p) => p + 1)}
              >
                {t('common.next')}
              </Button>
            </Stack>
          </Stack>
        </Paper>
      ) : null}

      <Menu
        open={menu != null}
        anchorEl={menu?.anchor}
        onClose={() => setMenu(null)}
      >
        {menu && canWrite ? (
          <MenuItem
            onClick={() => {
              setEditing(menu.receipt);
              setMenu(null);
            }}
          >
            {t('receipts.actionEdit')}
          </MenuItem>
        ) : null}
        {menu ? (
          <MenuItem
            onClick={() => {
              setSending(menu.receipt);
              setMenu(null);
            }}
          >
            {t('receipts.actionSend')}
          </MenuItem>
        ) : null}
        {menu && canWrite ? (
          <MenuItem
            onClick={() => {
              setManage(menu.receipt);
              setMenu(null);
            }}
          >
            {t('receipts.actionManage')}
          </MenuItem>
        ) : null}
        {menu && canCancel && !menu.receipt.gatewayPayment && toNumber(menu.receipt.allocatable ?? menu.receipt.unallocated) > 0 ? (
          <MenuItem
            onClick={() => {
              setRefunding(menu.receipt);
              setMenu(null);
            }}
          >
            {t('receipts.actionRefund')}
          </MenuItem>
        ) : null}
        {menu && canCancel && menu.receipt.customerIsWalkIn && toNumber(menu.receipt.unallocated) > 0 ? (
          <MenuItem
            onClick={() => {
              setReassigning(menu.receipt);
              setMenu(null);
            }}
          >
            {t('receipts.actionReassign')}
          </MenuItem>
        ) : null}
        {menu && canFixTill && menu.receipt.mode === 'CASH' && menu.receipt.shift ? (
          <MenuItem
            onClick={() => {
              setCorrecting(menu.receipt);
              setMenu(null);
            }}
          >
            {t('receipts.actionCorrectTill')}
          </MenuItem>
        ) : null}
        {menu && user && isOwner(user.role) && menu.receipt.gatewayPayment ? (
          <MenuItem
            onClick={() => {
              if (window.confirm(t('receipts.gatewayRefundConfirm'))) {
                gatewayRefund.mutate(menu.receipt.gatewayPayment!);
              }
              setMenu(null);
            }}
          >
            {t('receipts.actionGatewayRefund')}
          </MenuItem>
        ) : null}
      </Menu>

      <NewReceiptDialog
        open={open && canWrite}
        onClose={() => setOpen(false)}
        onQueued={() => void outbox.refresh()}
        onCreated={(text) => {
          setMessage(text);
          setError(null);
          setErrorSource(null);
        }}
      />
      <VoidReceiptDialog
        target={voidTarget ?? null}
        narrow={narrowVoid}
        pending={voidMutation.isPending}
        error={voidError}
        errorSource={voidErrorSource}
        onCancel={() => {
          setVoidId(null);
          setVoidError(null);
          setVoidErrorSource(null);
        }}
        onConfirm={(reason) => {
          if (voidId != null) voidMutation.mutate({ id: voidId, reason });
        }}
      />
      <AllocationManagerDialog
        receipt={manage}
        canCancel={canCancel}
        canWrite={canWrite}
        onClose={() => setManage(null)}
        onChanged={(text) => {
          setManage(null);
          done(text);
        }}
      />
      <EditReceiptDialog
        receipt={editing}
        onClose={() => setEditing(null)}
        onDone={() => {
          setEditing(null);
          setViewReceipt(null);
          done(t('receipts.editSaved'));
        }}
      />
      <RefundAdvanceDialog
        receipt={refunding}
        onClose={() => setRefunding(null)}
        onDone={() => {
          setRefunding(null);
          done(t('receipts.refundDone'));
        }}
      />
      <ReassignReceiptDialog
        receipt={reassigning}
        onClose={() => setReassigning(null)}
        onDone={() => {
          setReassigning(null);
          done(t('receipts.reassignDone'));
        }}
      />
      <CorrectClosedTillDialog
        receipt={correcting}
        onClose={() => setCorrecting(null)}
        onDone={() => {
          setCorrecting(null);
          done(t('receipts.tillDone'));
        }}
      />
      <SendReceiptDialog
        receipt={sending}
        onClose={() => setSending(null)}
        onDone={(text) => {
          setSending(null);
          setViewReceipt(null);
          setMessage(text);
        }}
      />
      {bulkOpen ? (
        <BulkAllocateDialog
          receipts={selectedRows}
          onClose={() => {
            setBulkOpen(false);
            setSelected(new Set());
          }}
          onDone={refreshAll}
        />
      ) : null}
      {bulkSendOpen ? (
        <BulkSendDialog
          receipts={selectedRows}
          onClose={() => {
            setBulkSendOpen(false);
            setSelected(new Set());
          }}
        />
      ) : null}
      <ReceiptVoucherDialog
        receipt={viewReceipt}
        onClose={() => setViewReceipt(null)}
        onManage={canWrite ? (r) => setManage(r) : undefined}
        onEdit={canWrite ? (r) => setEditing(r) : undefined}
        onSend={(r) => setSending(r)}
      />
    </Stack>
  );
}
