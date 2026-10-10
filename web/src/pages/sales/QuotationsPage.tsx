import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Autocomplete from '@mui/material/Autocomplete';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import IconButton from '@mui/material/IconButton';
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
import MoreVertIcon from '@mui/icons-material/MoreVert';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Navigate, useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import {
  cancelExpiredQuotations,
  cancelQuotation,
  closeQuotationRemaining,
  downloadSalesDocumentPdf,
  duplicateQuotation,
  getCompany,
  listQuotationsPage,
  quotationLifecycle,
  reopenClosedQuotation,
  type QuotationLifecycleAction,
} from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import {
  EMPTY_HISTORY_FILTERS,
  HistoryFilterBar,
  type HistoryFilters,
} from '@/components/HistoryFilterBar';
import { ShareQuotationDialog } from '@/components/ShareQuotationDialog';
import { StatusChip } from '@/components/StatusChip';
import { isRuntimeFlagEnabled, useFeatureFlagEpoch } from '@/config/featureFlags';
import { PageTitle } from '@/contextHelp';
import { useCustomerSearch } from '@/hooks/usePartySearch';
import { useDebouncedValue } from '@/hooks/useDebouncedValue';
import { useNotices } from '@/hooks/useNotices';
import { t } from '@/i18n';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import { ConvertQuotationDialog } from '@/pages/sales/ConvertQuotationDialog';
import { useQuotationConvert } from '@/pages/sales/useQuotationConvert';
import type { Customer, Quotation } from '@/types/domain';
import { triggerBlobDownload } from '@/utils/blob';
import { formatMoney, toNumber } from '@/utils/money';
import { canCancelDocuments, canCreateSales } from '@/utils/permissions';
import { isQuotationExpired, OPEN_QUOTATION_STATUSES } from '@/utils/quotationExpiry';
import { documentStatusTone, statusLabelKey } from '@/utils/status';

const PAGE_SIZE = 50;

type ReasonKind = 'cancel' | 'reject' | 'reopen' | 'close' | 'reopen-closed';

const REASON_TITLE: Record<ReasonKind, string> = {
  cancel: 'common.cancel',
  reject: 'phase1.quotationMarkRejected',
  reopen: 'phase1.quotationReopen',
  close: 'phase1.quotationCloseRemaining',
  'reopen-closed': 'phase1.quotationReopenClosed',
};

export function QuotationsPage() {
  const qc = useQueryClient();
  const { user } = useAuth();
  const canCreate = canCreateSales(user);
  const canCancel = canCancelDocuments(user);
  const isOwner = user?.role === 'OWNER';
  useFeatureFlagEpoch();
  const lifecycleOn = isRuntimeFlagEnabled('QUOTE_LIFECYCLE');
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const notices = useNotices();

  // A page that sent the user here (the editor, a convert) can pass a message to show once.
  const [flashDismissed, setFlashDismissed] = useState(false);
  const flash = !flashDismissed ? ((location.state as { message?: string } | null)?.message ?? null) : null;

  const [page, setPage] = useState(1);
  const [filters, setFilters] = useState<HistoryFilters>(EMPTY_HISTORY_FILTERS);
  const [filterCustomer, setFilterCustomer] = useState<Customer | null>(null);
  const filterCustomerSearch = useCustomerSearch({ selected: filterCustomer });
  // Sorting is done by the server so it covers every page, not just the one on screen.
  const [sort, setSort] = useState<{ field: string; desc: boolean }>({ field: 'quotation_date', desc: true });
  const debouncedQ = useDebouncedValue(filters.q, 300);
  const expiredOnly = filters.status === 'EXPIRED';
  const statusParam = expiredOnly ? undefined : filters.status === 'CLOSED' ? 'CONVERTED' : filters.status || undefined;

  const query = useQuery({
    queryKey: ['quotations', page, statusParam, expiredOnly, debouncedQ, filters.dateFrom, filters.dateTo, filterCustomer?.id ?? null, sort],
    queryFn: () =>
      listQuotationsPage({
        page,
        pageSize: PAGE_SIZE,
        status: statusParam,
        expired: expiredOnly ? true : undefined,
        q: debouncedQ || undefined,
        customer: filterCustomer?.id,
        date_from: filters.dateFrom || undefined,
        date_to: filters.dateTo || undefined,
        ordering: `${sort.desc ? '-' : ''}${sort.field}`,
      }),
  });
  const company = useQuery({ queryKey: ['company'], queryFn: getCompany });

  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ['quotations'] });
    void qc.invalidateQueries({ queryKey: ['quotation'] });
  };

  const convert = useQuotationConvert({ onDone: notices.success });

  // ---- one reason dialog for cancel, reject, reopen, close remaining and reopen closed
  const [reasonTarget, setReasonTarget] = useState<{ quotation: Quotation; kind: ReasonKind } | null>(null);
  const [reason, setReason] = useState('');
  const reasonRequired = reasonTarget != null && reasonTarget.kind !== 'cancel' && reasonTarget.kind !== 'reject';
  const settle = (message: string) => {
    setReasonTarget(null);
    setReason('');
    notices.success(message);
    refresh();
  };
  const failWith = (err: unknown) => {
    setReasonTarget(null);
    notices.fail(getErrorMessage(err));
  };
  const cancelMutation = useMutation({
    mutationFn: ({ id, text }: { id: number; text: string }) => cancelQuotation(id, text),
    onSuccess: () => settle(t('phase1.quotationCancelled')),
    onError: failWith,
  });
  const lifecycleMutation = useMutation({
    mutationFn: ({ id, action, text }: { id: number; action: QuotationLifecycleAction; text?: string }) =>
      quotationLifecycle(id, action, text),
    onSuccess: () => settle(t('phase1.quotationStatusUpdated')),
    onError: failWith,
  });
  const closeMutation = useMutation({
    mutationFn: ({ id, text }: { id: number; text: string }) => closeQuotationRemaining(id, text),
    onSuccess: () => settle(t('phase1.quotationStatusUpdated')),
    onError: failWith,
  });
  const reopenClosedMutation = useMutation({
    mutationFn: ({ id, text }: { id: number; text: string }) => reopenClosedQuotation(id, text),
    onSuccess: () => settle(t('phase1.quotationStatusUpdated')),
    onError: failWith,
  });
  const duplicateMutation = useMutation({
    mutationFn: (id: number) => duplicateQuotation(id),
    onSuccess: (copy) => {
      refresh();
      void navigate(`/sales/quotations/${copy.id}`, { state: { message: t('phase1.quotationDuplicated') } });
    },
    onError: (err) => notices.fail(getErrorMessage(err)),
  });
  const cancelExpiredMutation = useMutation({
    mutationFn: cancelExpiredQuotations,
    onSuccess: (res) => {
      refresh();
      const base = t('phase1.quotationCancelExpiredDone', { count: res.cancelled });
      notices.success(
        res.needsCloseRemaining.length > 0
          ? `${base}. ${t('phase1.quotationNeedsClose', {
              count: res.needsCloseRemaining.length,
              numbers: res.needsCloseRemaining.map((row) => row.number || `#${row.id}`).join(', '),
            })}`
          : base,
      );
    },
    onError: (err) => notices.fail(getErrorMessage(err)),
  });
  const [confirmCancelExpired, setConfirmCancelExpired] = useState(false);

  const submitReason = () => {
    if (!reasonTarget) return;
    const id = reasonTarget.quotation.id;
    const text = reason.trim();
    switch (reasonTarget.kind) {
      case 'cancel':
        return cancelMutation.mutate({ id, text });
      case 'reject':
        return lifecycleMutation.mutate({ id, action: 'mark-rejected', text });
      case 'reopen':
        return lifecycleMutation.mutate({ id, action: 'reopen-for-changes', text });
      case 'close':
        return closeMutation.mutate({ id, text });
      case 'reopen-closed':
        return reopenClosedMutation.mutate({ id, text });
    }
  };
  const reasonBusy =
    cancelMutation.isPending || lifecycleMutation.isPending || closeMutation.isPending || reopenClosedMutation.isPending;

  const [shareTarget, setShareTarget] = useState<Quotation | null>(null);
  const [menu, setMenu] = useState<{ anchor: HTMLElement; quotation: Quotation } | null>(null);

  const quotations = query.data?.results ?? [];
  const hasFilters = Boolean(filters.q || filters.status || filters.dateFrom || filters.dateTo || filterCustomer);
  const clearFilters = () => {
    setFilters(EMPTY_HISTORY_FILTERS);
    setFilterCustomer(null);
    filterCustomerSearch.setQuery('');
    setPage(1);
  };
  const downloadPdf = (q: Quotation) => {
    void downloadSalesDocumentPdf('quotation', q.id)
      .then((blob) => triggerBlobDownload(blob, `${q.number || q.id}.pdf`))
      .catch((err) => notices.fail(getErrorMessage(err)));
  };
  const sortHead = (field: string, label: string, align?: 'right') => (
    <TableCell align={align} sortDirection={sort.field === field ? (sort.desc ? 'desc' : 'asc') : false}>
      <TableSortLabel
        active={sort.field === field}
        direction={sort.desc ? 'desc' : 'asc'}
        onClick={() => {
          setSort((prev) => ({ field, desc: prev.field === field ? !prev.desc : field !== 'number' && field !== 'customer__name' }));
          setPage(1);
        }}
      >
        {label}
      </TableSortLabel>
    </TableCell>
  );

  const openReason = (quotation: Quotation, kind: ReasonKind) => {
    setReason('');
    setMenu(null);
    setReasonTarget({ quotation, kind });
  };

  const menuQuote = menu?.quotation ?? null;
  const menuItems = (() => {
    if (!menuQuote) return [];
    const q = menuQuote;
    const items: Array<{ label: string; onClick: () => void; tone?: 'error' }> = [];
    const noneConverted = (q.items ?? []).every((it) => toNumber(it.convertedQuantity) === 0);
    const closed = Boolean(q.shortClosedAt);
    if (q.status !== 'CANCELLED' && q.status !== 'REJECTED' && canCreate) {
      items.push({ label: t('phase1.quotationShare'), onClick: () => { setMenu(null); setShareTarget(q); } });
    }
    if (canCreate) {
      items.push({
        label: t('phase1.quotationDuplicate'),
        onClick: () => { setMenu(null); duplicateMutation.mutate(q.id); },
      });
    }
    if (lifecycleOn && canCreate && !closed) {
      if (q.status === 'DRAFT') {
        items.push({ label: t('phase1.quotationMarkSent'), onClick: () => { setMenu(null); notices.clear(); lifecycleMutation.mutate({ id: q.id, action: 'mark-sent' }); } });
      }
      if (q.status === 'SENT') {
        items.push({ label: t('phase1.quotationMarkAccepted'), onClick: () => { setMenu(null); notices.clear(); lifecycleMutation.mutate({ id: q.id, action: 'mark-accepted' }); } });
        items.push({ label: t('phase1.quotationMarkRejected'), onClick: () => openReason(q, 'reject') });
      }
      if (['SENT', 'ACCEPTED', 'REJECTED'].includes(q.status)) {
        items.push({ label: t('phase1.quotationReopen'), onClick: () => openReason(q, 'reopen') });
      }
    }
    if (canCancel && OPEN_QUOTATION_STATUSES.includes(q.status) && !closed && !noneConverted) {
      items.push({ label: t('phase1.quotationCloseRemaining'), onClick: () => openReason(q, 'close') });
    }
    if (isOwner && closed) {
      items.push({ label: t('phase1.quotationReopenClosed'), onClick: () => openReason(q, 'reopen-closed') });
    }
    if (canCancel && q.status === 'DRAFT' && noneConverted) {
      items.push({ label: t('common.cancel'), tone: 'error', onClick: () => openReason(q, 'cancel') });
    }
    return items;
  })();

  // Old links used ?create=1 to open the editor; it is a page now.
  if (canCreate && searchParams.get('create') === '1') {
    return <Navigate to="/sales/quotations/new" replace />;
  }

  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <PageTitle>{t('nav.quotations')}</PageTitle>
        <Stack direction="row" spacing={1}>
          {canCancel && expiredOnly && quotations.length > 0 ? (
            <Button variant="outlined" color="warning" onClick={() => setConfirmCancelExpired(true)}>
              {t('phase1.quotationCancelExpired')}
            </Button>
          ) : null}
          {canCreate ? (
            <Button variant="contained" onClick={() => void navigate('/sales/quotations/new')}>
              {t('phase1.newQuotation')}
            </Button>
          ) : null}
        </Stack>
      </Stack>
      {flash ? (
        <Alert severity="success" onClose={() => setFlashDismissed(true)}>
          {flash}
        </Alert>
      ) : null}
      {notices.message ? <Alert severity="success" onClose={notices.clear}>{notices.message}</Alert> : null}
      {notices.error ? <HelpErrorAlert message={notices.error} /> : null}
      <HistoryFilterBar
        value={filters}
        onChange={(next) => {
          setFilters(next);
          setPage(1);
        }}
        dateRangePresets
        statusOptions={[
          { value: 'OPEN', label: t('status.OPEN') },
          { value: 'EXPIRED', label: t('status.EXPIRED') },
          { value: 'CLOSED', label: t('status.converted') },
          ...(lifecycleOn
            ? [
                { value: 'SENT', label: t('status.SENT') },
                { value: 'ACCEPTED', label: t('status.ACCEPTED') },
                { value: 'REJECTED', label: t('status.REJECTED') },
              ]
            : []),
          { value: 'CANCELLED', label: t('status.cancelled') },
        ]}
        party={
          <Autocomplete
            size="small"
            sx={{ minWidth: 200 }}
            options={filterCustomerSearch.options}
            filterOptions={(options) => options}
            loading={filterCustomerSearch.isFetching}
            value={filterCustomer}
            isOptionEqualToValue={(option, value) => option.id === value.id}
            getOptionLabel={(option) => option.name}
            noOptionsText={t('common.noResults')}
            onInputChange={(_, value, why) => {
              if (why === 'input') filterCustomerSearch.setQuery(value);
              if (why === 'clear') filterCustomerSearch.setQuery('');
            }}
            onChange={(_, option) => {
              setFilterCustomer(option);
              setPage(1);
            }}
            renderInput={(params) => <TextField {...params} label={t('billing.customer')} />}
          />
        }
      />
      {query.isLoading ? <LoadingState /> : null}
      {query.isError ? (
        <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />
      ) : null}
      {quotations.length === 0 && query.isSuccess ? (
        hasFilters ? (
          <EmptyState
            description={t('phase1.quotationNoMatch')}
            action={<Button onClick={clearFilters}>{t('common.clearFilters')}</Button>}
          />
        ) : (
          <EmptyState description={t('empty.quotations')} />
        )
      ) : null}
      {quotations.length > 0 ? (
        <Paper tabIndex={0} role="region" aria-label={t('common.scrollableTable')} sx={{ overflow: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                {sortHead('number', t('common.number'))}
                {sortHead('quotation_date', t('common.date'))}
                {sortHead('valid_until', t('billing.validUntil'))}
                {sortHead('customer__name', t('billing.customer'))}
                <TableCell>{t('common.status')}</TableCell>
                {sortHead('grand_total', t('common.total'), 'right')}
                <TableCell />
              </TableRow>
            </TableHead>
            <TableBody>
              {quotations.map((q) => {
                const expired = isQuotationExpired(q);
                const closed = Boolean(q.shortClosedAt);
                const canConvert = OPEN_QUOTATION_STATUSES.includes(q.status) && canCreate && !closed;
                const busy = convert.pending && convert.busyId === q.id;
                return (
                  <TableRow key={q.id}>
                    <TableCell>{q.number ?? '—'}</TableCell>
                    <TableCell>{q.quotationDate}</TableCell>
                    <TableCell>
                      {q.validUntil ? (
                        <Stack direction="row" spacing={0.5} alignItems="center">
                          <span>{q.validUntil}</span>
                          {expired ? (
                            <Typography variant="caption" sx={{ color: 'error.main', fontWeight: 'bold' }}>
                              ({t('status.EXPIRED')})
                            </Typography>
                          ) : null}
                        </Stack>
                      ) : (
                        '—'
                      )}
                    </TableCell>
                    <TableCell>{q.customerName ?? '—'}</TableCell>
                    <TableCell>
                      <Stack direction="row" spacing={0.5} alignItems="center" flexWrap="wrap" useFlexGap>
                        <StatusChip tone={documentStatusTone(q.status)} labelKey={statusLabelKey(q.status)} />
                        {q.conversionState === 'PARTIAL' ? (
                          <Typography variant="caption" color="text.secondary">
                            {t('phase1.quotationPartlyConverted')}
                            {q.remainingTotal != null ? ` · ${t('phase1.quotationRemaining')} ${formatMoney(q.remainingTotal)}` : ''}
                          </Typography>
                        ) : null}
                        {closed ? (
                          <Typography variant="caption" color="warning.main" title={q.shortCloseReason}>
                            {t('phase1.quotationClosedChip')}
                          </Typography>
                        ) : null}
                        {q.sentAt && q.status === 'DRAFT' ? (
                          <Typography variant="caption" color="text.secondary">
                            {t('phase1.quotationSentOn', { date: q.sentAt.slice(0, 10) })}
                          </Typography>
                        ) : null}
                      </Stack>
                    </TableCell>
                    <TableCell align="right">{formatMoney(q.grandTotal)}</TableCell>
                    <TableCell align="right">
                      <Stack direction="row" spacing={1} justifyContent="flex-end" alignItems="center">
                        <Button size="small" variant="text" onClick={() => downloadPdf(q)}>
                          {t('common.download')}
                        </Button>
                        {q.status === 'DRAFT' && canCreate ? (
                          <Button size="small" variant="text" onClick={() => void navigate(`/sales/quotations/${q.id}/edit`)}>
                            {t('common.edit')}
                          </Button>
                        ) : (
                          <Button size="small" variant="text" onClick={() => void navigate(`/sales/quotations/${q.id}`)}>
                            {t('common.view')}
                          </Button>
                        )}
                        {canConvert ? (
                          <>
                            <Button size="small" variant="outlined" disabled={busy} onClick={() => { notices.clear(); convert.open(q, 'order'); }}>
                              {t('common.toOrder')}
                            </Button>
                            <Button size="small" disabled={busy} onClick={() => { notices.clear(); convert.open(q, 'invoice'); }}>
                              {t('common.convert')}
                            </Button>
                          </>
                        ) : null}
                        <IconButton
                          size="small"
                          aria-label={t('common.moreActions')}
                          onClick={(e) => setMenu({ anchor: e.currentTarget, quotation: q })}
                        >
                          <MoreVertIcon fontSize="small" />
                        </IconButton>
                      </Stack>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </Paper>
      ) : null}
      {query.data && (query.data.next || page > 1) ? (
        <Stack direction="row" spacing={1} justifyContent="flex-end" alignItems="center">
          <Typography variant="body2" color="text.secondary">
            {t('common.page')} {page}
            {query.data.count != null ? ` · ${query.data.count}` : ''}
          </Typography>
          <Button variant="outlined" size="small" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
            {t('common.previous')}
          </Button>
          <Button variant="outlined" size="small" disabled={!query.data.next} onClick={() => setPage((p) => p + 1)}>
            {t('common.next')}
          </Button>
        </Stack>
      ) : null}

      <Menu anchorEl={menu?.anchor ?? null} open={menu != null && menuItems.length > 0} onClose={() => setMenu(null)}>
        {menuItems.map((item) => (
          <MenuItem key={item.label} onClick={item.onClick} sx={item.tone === 'error' ? { color: 'error.main' } : undefined}>
            {item.label}
          </MenuItem>
        ))}
      </Menu>

      <Dialog open={reasonTarget != null} onClose={() => setReasonTarget(null)} aria-labelledby="quotation-reason-title">
        <DialogTitle id="quotation-reason-title">
          {reasonTarget ? t(REASON_TITLE[reasonTarget.kind]) : ''} {reasonTarget?.quotation.number ?? ''}
        </DialogTitle>
        <DialogContent>
          {reasonTarget?.kind === 'cancel' ? (
            <Typography variant="body2" sx={{ mb: 2 }}>{t('phase1.confirmCancelQuotation')}</Typography>
          ) : null}
          {reasonTarget?.kind === 'close' ? (
            <Typography variant="body2" sx={{ mb: 2 }}>{t('phase1.quotationCloseHelp')}</Typography>
          ) : null}
          <TextField
            fullWidth
            size="small"
            autoFocus
            required={reasonRequired}
            label={reasonRequired ? t('phase1.quotationReasonLabel') : t('phase1.quotationCancelReason')}
            value={reason}
            inputProps={{ maxLength: 500 }}
            onChange={(e) => setReason(e.target.value)}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setReasonTarget(null)}>{t('common.close')}</Button>
          <Button
            color={reasonTarget?.kind === 'cancel' ? 'error' : 'primary'}
            variant="contained"
            disabled={reasonBusy || (reasonRequired && !reason.trim())}
            onClick={submitReason}
          >
            {reasonTarget?.kind === 'cancel' ? t('common.cancel') : t('common.confirm')}
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={confirmCancelExpired} onClose={() => setConfirmCancelExpired(false)}>
        <DialogTitle>{t('phase1.quotationCancelExpired')}</DialogTitle>
        <DialogContent>
          <Typography variant="body2">{t('phase1.quotationCancelExpiredConfirm')}</Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmCancelExpired(false)}>{t('common.close')}</Button>
          <Button
            color="warning"
            variant="contained"
            disabled={cancelExpiredMutation.isPending}
            onClick={() => {
              setConfirmCancelExpired(false);
              cancelExpiredMutation.mutate();
            }}
          >
            {t('common.confirm')}
          </Button>
        </DialogActions>
      </Dialog>

      <ShareQuotationDialog
        open={shareTarget != null}
        quotation={shareTarget ? { id: shareTarget.id, number: shareTarget.number } : null}
        companyName={company.data?.name ?? ''}
        onClose={() => setShareTarget(null)}
        onShared={refresh}
      />
      <ConvertQuotationDialog
        quotation={convert.target?.quotation ?? null}
        mode={convert.target?.mode ?? null}
        pending={convert.pending}
        error={convert.error}
        onClose={convert.close}
        onConfirm={convert.confirm}
      />
    </Stack>
  );
}
